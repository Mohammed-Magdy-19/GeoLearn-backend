"""
apps/courses/views.py

DRF viewsets and API views for course content delivery.

All endpoints require JWT authentication by default (see REST_FRAMEWORK
settings). Specific actions that need to be public (free preview lesson
playback) are explicitly decorated with @permission_classes([AllowAny]).

Endpoints:
  GET    /api/courses/              — List published courses
  GET    /api/courses/<slug>/       — Course detail with modules & lessons
  GET    /api/courses/<slug>/lessons/<lesson_id>/ — Lesson detail + session token
  POST   /api/courses/progress/     — Report watch position
  GET    /api/courses/progress/     — List user's progress entries
  GET    /api/courses/continue/     — Get the most recently watched lesson

Secure Video Subsystem endpoints:
  GET    /api/v1/videos/<video_id>/meta   — Video metadata (title, duration, thumbnail)
  GET    /api/v1/videos/<video_id>/stream — Secure blob stream (requires X-Playback-Token)
"""

from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Count
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination

from .models import Course, Module, Lesson, LessonProgress, VideoSession, Enrollment, Summary, MetadataEntry, SpatialDataEntry
from .serializers import (
    CourseListSerializer,
    CourseDetailSerializer,
    LessonDetailSerializer,
    LessonListSerializer,
    LessonProgressSerializer,
    LessonProgressReportSerializer,
    VideoSessionSerializer,
    EnrollmentSerializer,
    SummaryListSerializer,
    PublicMetadataSerializer,
    PublicSpatialDataSerializer,
)
from .secure_video_service import (
    check_lesson_access,
    create_video_session,
    validate_session_token,
    revoke_session,
    serve_secure_stream,
    get_video_metadata,
)


# ─────────────────────────────────────────────────────────────
# Pagination Class
# ─────────────────────────────────────────────────────────────

class CoursePagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100


# ─────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────

def check_course_access(user, course: Course) -> bool:
    """
    Determine if the user can access the full content of a course.

    Access is granted when any of:
      • The course is free (price == 0)
      • The user is staff / superuser
      • The user has a successful payment record (Phase 3)
    """
    if course.price_egp == 0:
        return True
    if user.is_staff or user.is_superuser:
        return True

    # TODO(Phase 3): Check PaymentTransaction for actual purchase
    # from apps.payments.models import PaymentTransaction
    # return PaymentTransaction.objects.filter(
    #     user=user, course=course, status="SUCCESS"
    # ).exists()

    return False  # Conservative default


# ─────────────────────────────────────────────────────────────
# Course list & detail
# ─────────────────────────────────────────────────────────────

class CourseListView(generics.ListAPIView):
    """
    GET /api/courses/

    Returns a paginated list of published courses.
    Supports ?search=<query> to filter by title.
    """

    serializer_class = CourseListSerializer
    permission_classes = [AllowAny]
    pagination_class = CoursePagination

    def get_queryset(self):
        queryset = (
            Course.objects.filter(is_published=True)
            .annotate(
                module_count=Count("modules", distinct=True),
                lesson_count=Count("modules__lessons", distinct=True),
            )
            .order_by("-created_at")
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset


class CourseDetailView(generics.RetrieveAPIView):
    """
    GET /api/courses/<slug>/

    Returns full course detail including nested modules and lessons.
    """

    serializer_class = CourseDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Course.objects.filter(is_published=True).prefetch_related(
            Prefetch(
                "modules",
                queryset=Module.objects.prefetch_related(
                    Prefetch("lessons", queryset=Lesson.objects.order_by("order_index"))
                ).order_by("order_index"),
            )
        )


# ─────────────────────────────────────────────────────────────
# Lesson detail (with secure video metadata & session token)
# ─────────────────────────────────────────────────────────────

class LessonDetailView(APIView):
    """
    GET /api/courses/<slug>/lessons/<lesson_id>/

    Returns lesson details including:
      • Secure video metadata (UUID reference, duration, thumbnail)
      • A short-lived session token for blob stream requests
      • User's current progress (last watched position)

    Access rules:
      • Free-preview lessons: any authenticated user
      • Paid lessons: user must have purchased the parent course
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, slug: str, lesson_id: str):
        # Resolve the course and lesson
        course = get_object_or_404(Course, slug=slug, is_published=True)
        lesson = get_object_or_404(
            Lesson.objects.select_related("module__course"),
            id=lesson_id,
            module__course=course,
        )

        # Access control
        if not lesson.is_free_preview:
            if not check_course_access(request.user, course):
                raise PermissionDenied(
                    detail="Purchase required to access this lesson."
                )

        serializer = LessonDetailSerializer(
            lesson,
            context={"request": request},
        )
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────
# Lesson list within a module (for sidebar navigation)
# ─────────────────────────────────────────────────────────────

class ModuleLessonListView(APIView):
    """
    GET /api/courses/<slug>/modules/<module_id>/lessons/

    Returns all lessons for a given module.
    Used by the player's sidebar navigation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, slug: str, module_id: str):
        course = get_object_or_404(Course, slug=slug, is_published=True)
        module = get_object_or_404(
            Module, id=module_id, course=course
        )

        lessons = Lesson.objects.filter(module=module).order_by("order_index")
        serializer = LessonListSerializer(lessons, many=True)
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────
# Secure Video Subsystem — Metadata endpoint
# ─────────────────────────────────────────────────────────────

class VideoMetadataView(APIView):
    """
    GET /api/v1/videos/<video_id>/meta

    Returns video metadata for the Secure Video Subsystem frontend.
    Response format matches the VideoMetadata interface:
        { id, title, thumbnail, duration_seconds, is_free_preview }

    Requires authentication. The frontend uses this to populate
    the player UI before requesting the blob stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, video_id: str):
        # Resolve the lesson by secure_video_id
        lesson = get_object_or_404(
            Lesson.objects.select_related("module__course"),
            secure_video_id=video_id,
        )

        # Access control
        if not check_lesson_access(request.user, lesson):
            raise PermissionDenied(
                detail="You do not have access to this video."
            )

        metadata = get_video_metadata(lesson)
        return Response(metadata)


# ─────────────────────────────────────────────────────────────
# Secure Video Subsystem — Stream endpoint
# ─────────────────────────────────────────────────────────────

class VideoStreamView(APIView):
    """
    GET /api/v1/videos/<video_id>/stream

    Serves the actual video file as a secure blob stream.

    Authentication: X-Playback-Token header (required)
    The token is obtained from the lesson detail endpoint.

    Security measures:
      • Validates the session token before serving
      • Sets anti-caching headers (no-store, no-cache)
      • Sets anti-download headers (inline disposition)
      • Returns the file as a binary blob for frontend consumption
    """

    # No default permission/authentication classes — we handle auth via X-Playback-Token
    permission_classes = []
    authentication_classes = []

    def get(self, request, video_id: str):
        # Extract session token from header
        token = request.headers.get("X-Playback-Token")
        if not token:
            return Response(
                {"detail": "X-Playback-Token header is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Validate the session token
        session = validate_session_token(token)
        if not session:
            return Response(
                {"detail": "Invalid or expired session token."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Verify the session matches the requested video
        lesson = session.lesson
        if str(lesson.secure_video_id) != video_id:
            return Response(
                {"detail": "Session token does not match requested video."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Serve the secure stream
        return serve_secure_stream(lesson.secure_video_id, request)


# ─────────────────────────────────────────────────────────────
# Progress reporting & retrieval
# ─────────────────────────────────────────────────────────────

class LessonProgressReportView(APIView):
    """
    POST /api/courses/progress/

    Accepts a watch-position report from the video player.
    Expected body:
        { "lesson_id": "<uuid>", "last_watched_second": 42 }

    The endpoint creates or updates the LessonProgress row and
    auto-calculates completion when >= 90 % is watched.

    Throttled client-side to one call every 10 seconds.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LessonProgressReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lesson_id = serializer.validated_data["lesson_id"]
        last_watched_second = serializer.validated_data["last_watched_second"]

        # Resolve the lesson
        lesson = get_object_or_404(Lesson, id=lesson_id)

        # Ensure the user has access to this lesson
        course = lesson.module.course
        if not lesson.is_free_preview and not check_course_access(
            request.user, course
        ):
            raise PermissionDenied(
                detail="You do not have access to this lesson."
            )

        # Upsert the progress record
        progress, created = LessonProgress.objects.update_or_create(
            user=request.user,
            lesson=lesson,
            defaults={
                "last_watched_second": last_watched_second,
            },
        )

        # Auto-check completion
        progress.mark_completed(threshold_percent=90.0)
        progress.refresh_from_db()

        return Response(
            LessonProgressSerializer(progress).data,
            status=status.HTTP_200_OK,
        )


class LessonProgressListView(generics.ListAPIView):
    """
    GET /api/courses/progress/

    Returns the authenticated user's lesson progress entries,
    ordered by most recently updated first.
    """

    serializer_class = LessonProgressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LessonProgress.objects.filter(
            user=self.request.user
        ).select_related("lesson", "lesson__module", "lesson__module__course")


class ContinueLearningView(APIView):
    """
    GET /api/courses/continue/

    Returns the lesson the user was most recently watching,
    including the resume timestamp and secure video metadata.

    Used by the dashboard "Continue Learning" card.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Find the most recently updated progress entry
        progress = (
            LessonProgress.objects.filter(user=request.user)
            .select_related("lesson", "lesson__module", "lesson__module__course")
            .order_by("-updated_at")
            .first()
        )

        if not progress:
            return Response(
                {"detail": "No progress found. Start a course to begin learning."},
                status=status.HTTP_404_NOT_FOUND,
            )

        lesson = progress.lesson

        # Check access
        course = lesson.module.course
        if not lesson.is_free_preview and not check_course_access(
            request.user, course
        ):
            return Response(
                {"detail": "Purchase required to continue this lesson."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Build response combining lesson detail + progress
        lesson_serializer = LessonDetailSerializer(
            lesson,
            context={"request": request},
        )

        return Response(
            {
                "lesson": lesson_serializer.data,
                "progress": {
                    "last_watched_second": progress.last_watched_second,
                    "is_completed": progress.is_completed,
                },
                "course": {
                    "id": str(course.id),
                    "title": course.title,
                    "slug": course.slug,
                },
            }
        )


# ─────────────────────────────────────────────────────────────
# Session management endpoints
# ─────────────────────────────────────────────────────────────

class VideoSessionListView(generics.ListAPIView):
    """
    GET /api/courses/sessions/

    Returns the authenticated user's active video playback sessions.
    Useful for debugging and session management.
    """

    serializer_class = VideoSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VideoSession.objects.filter(
            user=self.request.user,
            is_revoked=False,
            expires_at__gt=timezone.now(),
        ).select_related("lesson", "lesson__module__course")


class VideoSessionRevokeView(APIView):
    """
    POST /api/courses/sessions/revoke/

    Revokes a specific video session token.
    Expected body: { "token": "<session_token>" }

    Also used for logout cleanup — revokes all sessions if no token provided.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("token")

        if token:
            # Revoke specific token
            success = revoke_session(token)
            if not success:
                return Response(
                    {"detail": "Session not found or already revoked."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {"detail": "Session revoked successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            # Revoke all user sessions (logout cleanup)
            from .secure_video_service import revoke_all_user_sessions
            count = revoke_all_user_sessions(request.user)
            return Response(
                {"detail": f"Revoked {count} session(s)."},
                status=status.HTTP_200_OK,
            )


# ─────────────────────────────────────────────────────────────
# Enrollment views
# ─────────────────────────────────────────────────────────────

class EnrollView(generics.CreateAPIView):
    """
    POST /api/courses/enroll/

    Enroll the authenticated user in a course.
    """
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.validated_data["course"]

        # Check if already enrolled
        enrollment, created = Enrollment.objects.get_or_create(
            user=request.user,
            course=course
        )

        response_serializer = self.get_serializer(enrollment)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(response_serializer.data, status=status_code)


class MyEnrollmentsView(generics.ListAPIView):
    """
    GET /api/courses/my-enrollments/

    Returns all course enrollments for the authenticated user.
    """
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Enrollment.objects.filter(
            user=self.request.user
        ).select_related("course")


class CourseProgressView(APIView):
    """
    GET /api/courses/<uuid>/progress/

    Returns overall and per-module progress for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id: str):
        # Resolve the course
        course = get_object_or_404(Course, id=course_id)

        # Get all lessons for this course
        lessons = Lesson.objects.filter(module__course=course)
        total_lessons = lessons.count()

        # Get completed progress entries for this user
        progress_entries = LessonProgress.objects.filter(
            user=request.user,
            lesson__in=lessons
        )
        completed_lessons = progress_entries.filter(is_completed=True).count()

        progress_percent = (
            (completed_lessons / total_lessons) * 100.0 if total_lessons > 0 else 0.0
        )

        # Calculate modules progress
        modules_progress = []
        for module in course.modules.all():
            module_lessons = lessons.filter(module=module)
            mod_total = module_lessons.count()
            mod_completed = progress_entries.filter(
                lesson__in=module_lessons,
                is_completed=True
            ).count()

            modules_progress.append({
                "id": str(module.id),
                "title": module.title,
                "total_lessons": mod_total,
                "completed_lessons": mod_completed,
                "progress_percent": (
                    (mod_completed / mod_total) * 100.0 if mod_total > 0 else 0.0
                ),
            })

        return Response({
            "course_id": str(course.id),
            "total_lessons": total_lessons,
            "completed_lessons": completed_lessons,
            "progress_percent": round(progress_percent, 1),
            "modules_progress": modules_progress
        })


# ─────────────────────────────────────────────────────────────
# Summaries (public)
# ─────────────────────────────────────────────────────────────

class SummaryListView(generics.ListAPIView):
    """
    GET /api/courses/summaries/

    Returns published summaries.
    Authenticated users only.
    """
    serializer_class = SummaryListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Summary.objects.filter(is_published=True)


class SummaryDownloadView(APIView):
    """
    POST /api/courses/summaries/<id>/download/

    Increments the download counter and returns the file URL.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, summary_id: str):
        summary = get_object_or_404(Summary, id=summary_id, is_published=True)
        summary.download_count += 1
        summary.save(update_fields=["download_count"])
        return Response({
            "file_url": request.build_absolute_uri(summary.file.url),
            "download_count": summary.download_count,
        })


# ─────────────────────────────────────────────────────────────
# Metadata (public)
# ─────────────────────────────────────────────────────────────

class MetadataListView(generics.ListAPIView):
    """
    GET /api/courses/metadata/

    Returns published metadata entries.
    Authenticated users only.
    """
    serializer_class = PublicMetadataSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MetadataEntry.objects.filter(is_published=True)


# ─────────────────────────────────────────────────────────────
# Spatial Data (public)
# ─────────────────────────────────────────────────────────────

class SpatialDataListView(generics.ListAPIView):
    """
    GET /api/courses/spatial-data/

    Returns published spatial data entries.
    Authenticated users only.
    """
    serializer_class = PublicSpatialDataSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SpatialDataEntry.objects.filter(is_published=True)