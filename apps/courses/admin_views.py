import uuid
from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.pagination import PageNumberPagination

from apps.courses.models import Course, Module, Lesson, LessonProgress, VideoSession, Enrollment, Summary, MetadataEntry, SpatialDataEntry
from apps.courses.secure_video_service import get_secure_video_config
from apps.notifications.services import create_system_notification
from .admin_serializers import (
    AdminCourseSerializer,
    AdminCourseDetailSerializer,
    AdminModuleSerializer,
    AdminLessonSerializer,
    AdminSummarySerializer,
    AdminMetadataSerializer,
    AdminSpatialDataSerializer,
)

User = get_user_model()

class AdminPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

class StatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        total_users = User.objects.count()
        new_users = User.objects.filter(date_joined__gte=start_of_month).count()
        total_courses = Course.objects.count()
        total_lessons = Lesson.objects.count()
        total_video_sessions = VideoSession.objects.count()
        active_sessions = VideoSession.objects.filter(is_revoked=False, expires_at__gt=now).count()
        total_completions = LessonProgress.objects.filter(is_completed=True).count()
        
        progress_entries = LessonProgress.objects.all()
        avg_progress = 0.0
        if progress_entries.exists():
            completed_count = progress_entries.filter(is_completed=True).count()
            avg_progress = (completed_count / progress_entries.count()) * 100.0
        
        return Response({
            "totalUsers": total_users,
            "newUsersThisMonth": new_users,
            "totalCourses": total_courses,
            "totalLessons": total_lessons,
            "totalVideoSessions": total_video_sessions,
            "activeSessions": active_sessions,
            "totalCompletions": total_completions,
            "avgProgressPercent": round(avg_progress, 1),
            "totalRevenueEgp": 0.0,
        })

class EnrollmentTrendsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        import calendar
        trends = []
        now = timezone.now()
        for i in range(5, -1, -1):
            month_date = now - timedelta(days=i*30)
            year = month_date.year
            month = month_date.month
            month_name = calendar.month_abbr[month] + f" {year}"
            
            enrollments = Enrollment.objects.filter(
                enrolled_at__year=year,
                enrolled_at__month=month
            ).count()
            
            completions = LessonProgress.objects.filter(
                is_completed=True,
                updated_at__year=year,
                updated_at__month=month
            ).count()
            
            trends.append({
                "month": month_name,
                "enrollments": enrollments,
                "completions": completions
            })
            
        return Response(trends)

class CoursePopularityView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        courses = Course.objects.all()
        popularity = []
        for course in courses:
            enrolled_count = Enrollment.objects.filter(course=course).count()
            
            lessons = Lesson.objects.filter(module__course=course)
            progress_entries = LessonProgress.objects.filter(lesson__in=lessons)
            avg_prog = 0.0
            if progress_entries.exists() and lessons.count() > 0:
                user_progress = progress_entries.values('user').annotate(
                    completed=Count('id', filter=Q(is_completed=True))
                )
                total_percent = sum((up['completed'] / lessons.count()) * 100.0 for up in user_progress)
                avg_prog = total_percent / len(user_progress) if len(user_progress) > 0 else 0.0
                
            popularity.append({
                "courseId": str(course.id),
                "courseTitle": course.title,
                "enrolledCount": enrolled_count,
                "avgProgress": round(avg_prog, 1),
            })
            
        popularity.sort(key=lambda x: x["enrolledCount"], reverse=True)
        return Response(popularity[:5])

class AdminCourseViewSet(ModelViewSet):
    permission_classes = [IsAdminUser]
    queryset = Course.objects.all().order_by("-created_at")
    pagination_class = AdminPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AdminCourseDetailSerializer
        return AdminCourseSerializer

    def perform_create(self, serializer):
        course = serializer.save()
        create_system_notification(
            title="🎓 كورس جديد",
            message=f'تم إضافة كورس جديد: "{course.title}"',
            link=f"/courses/{course.slug}",
        )

    def perform_update(self, serializer):
        course = serializer.save()
        create_system_notification(
            title="📝 تحديث كورس",
            message=f'تم تحديث كورس: "{course.title}"',
            link=f"/courses/{course.slug}",
        )

    def perform_destroy(self, instance):
        title = instance.title
        instance.delete()
        create_system_notification(
            title="🗑️ حذف كورس",
            message=f'تم حذف الكورس: "{title}"',
        )

class AdminModuleViewSet(ModelViewSet):
    permission_classes = [IsAdminUser]
    queryset = Module.objects.all().order_by("order_index")
    serializer_class = AdminModuleSerializer

class AdminLessonViewSet(ModelViewSet):
    permission_classes = [IsAdminUser]
    queryset = Lesson.objects.all().order_by("order_index")
    serializer_class = AdminLessonSerializer

    def _handle_video_file(self, lesson, request):
        """
        If a video_file was included in the request, save it to the
        secure video store and update the lesson's secure_video_id.
        The duration_seconds is expected from the client (browser-read).
        """
        video_file = request.FILES.get("video_file")
        if not video_file:
            return

        config = get_secure_video_config()
        stream_path = Path(config["stream_path"])
        stream_path.mkdir(parents=True, exist_ok=True)

        # If replacing an existing video, remove the old file
        if lesson.secure_video_id:
            for ext in [".mp4", ".webm", ".mkv"]:
                old_path = stream_path / f"{lesson.secure_video_id}{ext}"
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass

        # Save the new video file
        new_secure_video_id = uuid.uuid4()
        ext = Path(video_file.name).suffix or ".mp4"
        full_path = stream_path / f"{new_secure_video_id}{ext}"

        with open(full_path, "wb+") as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)

        lesson.secure_video_id = new_secure_video_id
        lesson.save(update_fields=["secure_video_id", "updated_at"])

    def perform_create(self, serializer):
        lesson = serializer.save()
        self._handle_video_file(lesson, self.request)
        create_system_notification(
            title="📚 درس جديد",
            message=f'تم إضافة درس جديد: "{lesson.title}"',
            link=f"/courses/{lesson.module.course.slug}",
        )

    def perform_update(self, serializer):
        lesson = serializer.save()
        self._handle_video_file(lesson, self.request)
        create_system_notification(
            title="📝 تحديث درس",
            message=f'تم تحديث الدرس: "{lesson.title}"',
            link=f"/courses/{lesson.module.course.slug}",
        )

    def perform_destroy(self, instance):
        title = instance.title
        slug = instance.module.course.slug
        # Clean up video file on disk before deleting the lesson
        if instance.secure_video_id:
            config = get_secure_video_config()
            stream_path = Path(config["stream_path"])
            for ext in [".mp4", ".webm", ".mkv"]:
                file_path = stream_path / f"{instance.secure_video_id}{ext}"
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
        instance.delete()
        create_system_notification(
            title="🗑️ حذف درس",
            message=f'تم حذف الدرس: "{title}"',
            link=f"/courses/{slug}",
        )

class VideoUploadView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        POST /api/admin/videos/upload/

        Uploads a video file for a lesson.
        - If the lesson already has a video, the old file is deleted from disk
          before the new one is saved (replace / update scenario).
        - Sets secure_video_id to a new UUID and updates duration_seconds.

        Note: duration_seconds is set to a placeholder (300 s) because
        server-side video probing (e.g. ffprobe) is not yet integrated.
        Real duration extraction can be added here when needed.
        """
        lesson_id = request.data.get("lesson_id")
        video_file = request.FILES.get("video_file")

        if not lesson_id or not video_file:
            return Response(
                {"detail": "Both lesson_id and video_file are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson = get_object_or_404(Lesson, id=lesson_id)

        config = get_secure_video_config()
        stream_path = Path(config["stream_path"])
        stream_path.mkdir(parents=True, exist_ok=True)

        # ── If a previous video exists, remove its file from disk ──────────
        if lesson.secure_video_id:
            for ext in [".mp4", ".webm", ".mkv"]:
                old_path = stream_path / f"{lesson.secure_video_id}{ext}"
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass  # Non-fatal; continue with the upload

        # ── Save the new video file ─────────────────────────────────────────
        new_secure_video_id = uuid.uuid4()
        ext = Path(video_file.name).suffix or ".mp4"
        full_path = stream_path / f"{new_secure_video_id}{ext}"

        with open(full_path, "wb+") as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)

        # ── Update lesson record ────────────────────────────────────────────
        # Placeholder duration: replace with ffprobe integration if needed.
        duration_seconds = 300

        lesson.secure_video_id = new_secure_video_id
        lesson.duration_seconds = duration_seconds
        lesson.save(update_fields=["secure_video_id", "duration_seconds", "updated_at"])

        create_system_notification(
            title="🎬 فيديو جديد",
            message=f'تم رفع فيديو جديد في الدرس: "{lesson.title}"',
            link=f"/courses/{lesson.module.course.slug}",
        )

        return Response(
            {
                "secure_video_id": str(new_secure_video_id),
                "duration_seconds": duration_seconds,
            },
            status=status.HTTP_200_OK,
        )


class VideoDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, secure_video_id: str):
        """
        DELETE /api/admin/videos/<secure_video_id>/

        Deletes the physical video file from disk, clears the lesson's
        secure_video_id, and resets duration_seconds to 0.
        """
        lesson = get_object_or_404(Lesson, secure_video_id=secure_video_id)

        # Remove the physical file from disk
        config = get_secure_video_config()
        stream_path = Path(config["stream_path"])
        for ext in [".mp4", ".webm", ".mkv"]:
            file_path = stream_path / f"{secure_video_id}{ext}"
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass  # Log in production; don't block the DB cleanup

        # Clear video reference and reset duration on the lesson
        lesson.secure_video_id = None
        lesson.duration_seconds = 0
        lesson.save(update_fields=["secure_video_id", "duration_seconds", "updated_at"])

        create_system_notification(
            title="🗑️ حذف فيديو",
            message=f'تم حذف فيديو الدرس: "{lesson.title}"',
            link=f"/courses/{lesson.module.course.slug}",
        )

        return Response(
            {"detail": "Video deleted successfully."},
            status=status.HTTP_200_OK,
        )


class AdminSummaryViewSet(ModelViewSet):
    """Full CRUD for summaries (admin only)."""
    permission_classes = [IsAdminUser]
    queryset = Summary.objects.all()
    serializer_class = AdminSummarySerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(subject__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        summary = serializer.save()
        create_system_notification(
            title="📄 ملخص جديد",
            message=f'تم إضافة ملخص جديد: "{summary.title}"',
            link="/summaries",
        )

    def perform_update(self, serializer):
        summary = serializer.save()
        create_system_notification(
            title="📝 تحديث ملخص",
            message=f'تم تحديث الملخص: "{summary.title}"',
            link="/summaries",
        )

    def perform_destroy(self, instance):
        title = instance.title
        instance.delete()
        create_system_notification(
            title="🗑️ حذف ملخص",
            message=f'تم حذف الملخص: "{title}"',
        )


# ─────────────────────────────────────────────────────────────
# Admin Metadata ViewSet
# ─────────────────────────────────────────────────────────────

class AdminMetadataViewSet(ModelViewSet):
    """Full CRUD for metadata entries (admin only)."""
    queryset = MetadataEntry.objects.all()
    serializer_class = AdminMetadataSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(category__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        entry = serializer.save()
        create_system_notification(
            title="📋 بيان وصفي جديد",
            message=f'تم إضافة بيان وصفي: "{entry.title}"',
            link="/metadata",
        )

    def perform_update(self, serializer):
        entry = serializer.save()
        create_system_notification(
            title="✏️ تحديث بيان وصفي",
            message=f'تم تحديث البيان الوصفي: "{entry.title}"',
            link="/metadata",
        )

    def perform_destroy(self, instance):
        title = instance.title
        instance.delete()
        create_system_notification(
            title="🗑️ حذف بيان وصفي",
            message=f'تم حذف البيان الوصفي: "{title}"',
        )


# ─────────────────────────────────────────────────────────────
# Admin Spatial Data ViewSet
# ─────────────────────────────────────────────────────────────

class AdminSpatialDataViewSet(ModelViewSet):
    """Full CRUD for spatial data entries (admin only)."""
    queryset = SpatialDataEntry.objects.all()
    serializer_class = AdminSpatialDataSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(category__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        entry = serializer.save()
        create_system_notification(
            title="🗺️ بيان مكاني جديد",
            message=f'تم إضافة بيان مكاني: "{entry.title}"',
            link="/spatial-data",
        )

    def perform_update(self, serializer):
        entry = serializer.save()
        create_system_notification(
            title="✏️ تحديث بيان مكاني",
            message=f'تم تحديث البيان المكاني: "{entry.title}"',
            link="/spatial-data",
        )

    def perform_destroy(self, instance):
        title = instance.title
        instance.delete()
        create_system_notification(
            title="🗑️ حذف بيان مكاني",
            message=f'تم حذف البيان المكاني: "{title}"',
        )
