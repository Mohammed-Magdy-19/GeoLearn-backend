"""
apps/courses/serializers.py

DRF serializers for the courses app.

Serializers handle:
  • Flattening the Course -> Module -> Lesson hierarchy for API responses
  • Read-only Lesson serializer that provides secure video metadata (not URLs)
  • Write-only LessonProgress serializer for position reporting
  • VideoSession serializer for playback token management

Security note:
  • No direct video URLs are ever exposed in API responses.
  • The frontend requests blob streams via X-Playback-Token headers.
  • Metadata endpoints provide only UUID references and duration info.
"""

import uuid
from rest_framework import serializers

from .models import Course, Module, Lesson, LessonProgress, VideoSession, Enrollment, Summary, MetadataEntry, SpatialDataEntry
from .secure_video_service import (
    get_video_metadata,
    create_video_session,
    check_lesson_access,
)


# ─────────────────────────────────────────────────────────────
# Lesson serializers
# ─────────────────────────────────────────────────────────────

class LessonListSerializer(serializers.ModelSerializer):
    """
    Lightweight lesson representation for nested listing inside a Module.
    Does not include any video reference — used in catalog/sidebar views.
    """

    duration_display = serializers.SerializerMethodField()
    has_video = serializers.BooleanField(read_only=True)
    progress = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    lesson_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "description",
            "order_index",
            "duration_seconds",
            "duration_display",
            "is_free_preview",
            "has_video",
            "lesson_file_url",
            "progress",
            "is_completed",
        ]

    def get_duration_display(self, obj: Lesson) -> str:
        """Format duration as MM:SS for UI display."""
        minutes, seconds = divmod(obj.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_progress(self, obj: Lesson) -> dict | None:
        """
        Return the user's progress for this lesson, if any.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            progress = LessonProgress.objects.get(
                user=request.user,
                lesson=obj,
            )
            return {
                "last_watched_second": progress.last_watched_second,
                "is_completed": progress.is_completed,
                "updated_at": progress.updated_at.isoformat(),
            }
        except LessonProgress.DoesNotExist:
            return None

    def get_is_completed(self, obj: Lesson) -> bool:
        """
        Return whether this lesson is completed by the user.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return LessonProgress.objects.filter(
            user=request.user,
            lesson=obj,
            is_completed=True
        ).exists()

    def get_lesson_file_url(self, obj: Lesson) -> str | None:
        if obj.lesson_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.lesson_file.url)
        return None


class LessonDetailSerializer(serializers.ModelSerializer):
    """
    Full lesson representation including secure video metadata.

    The `video_metadata` field provides the UUID reference and duration
    needed by the frontend to request a blob stream. It does NOT include
    any direct URL.

    The `session_token` field is generated on-demand for authenticated
    users who have access to the lesson. This token must be sent in the
    X-Playback-Token header for subsequent stream requests.

    The `progress` field shows the user's last watch position (if any).
    """

    duration_display = serializers.SerializerMethodField()
    video_metadata = serializers.SerializerMethodField()
    session_token = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    has_video = serializers.BooleanField(read_only=True)
    lesson_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "description",
            "order_index",
            "duration_seconds",
            "duration_display",
            "is_free_preview",
            "has_video",
            "secure_video_id",
            "video_metadata",
            "session_token",
            "progress",
            "lesson_file_url",
        ]

    def get_duration_display(self, obj: Lesson) -> str:
        minutes, seconds = divmod(obj.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_video_metadata(self, obj: Lesson) -> dict | None:
        """
        Return secure video metadata (UUID reference, duration, thumbnail).
        Returns None if the lesson has no associated video.
        """
        if not obj.has_video:
            return None
        return get_video_metadata(obj)

    def get_session_token(self, obj: Lesson) -> str | None:
        """
        Generate a short-lived playback session token for the requesting user.
        Returns None if the user is not authenticated or lacks access.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        user = request.user
        if not check_lesson_access(user, obj):
            return None

        # Create or refresh a session token for this user + lesson
        session = create_video_session(user, obj)
        return session.token

    def get_progress(self, obj: Lesson) -> dict | None:
        """
        Return the user's progress for this lesson, if any.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        try:
            progress = LessonProgress.objects.get(
                user=request.user,
                lesson=obj,
            )
            return {
                "last_watched_second": progress.last_watched_second,
                "is_completed": progress.is_completed,
                "updated_at": progress.updated_at.isoformat(),
            }
        except LessonProgress.DoesNotExist:
            return None

    def get_lesson_file_url(self, obj: Lesson) -> str | None:
        if obj.lesson_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.lesson_file.url)
        return None


# ─────────────────────────────────────────────────────────────
# Module serializers
# ─────────────────────────────────────────────────────────────

class ModuleSerializer(serializers.ModelSerializer):
    """
    Module representation including nested lessons.
    """

    lessons = LessonListSerializer(many=True, read_only=True)
    lesson_count = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id",
            "title",
            "description",
            "order_index",
            "lesson_count",
            "lessons",
        ]

    def get_lesson_count(self, obj: Module) -> int:
        return obj.lessons.count()


# ─────────────────────────────────────────────────────────────
# Course serializers
# ─────────────────────────────────────────────────────────────

class CourseListSerializer(serializers.ModelSerializer):
    """
    Lightweight course card — used in catalog listing.
    """

    module_count = serializers.SerializerMethodField()
    lesson_count = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail_url",
            "price_egp",
            "is_published",
            "module_count",
            "lesson_count",
            "created_at",
        ]

    def get_module_count(self, obj: Course) -> int:
        return obj.modules.count()

    def get_lesson_count(self, obj: Course) -> int:
        return Lesson.objects.filter(module__course=obj).count()

    def get_thumbnail_url(self, obj: Course) -> str | None:
        if obj.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
        return None


class CourseDetailSerializer(serializers.ModelSerializer):
    """
    Full course representation with nested modules and lessons.
    Used on the course detail / player page.
    """

    modules = ModuleSerializer(many=True, read_only=True)
    module_count = serializers.SerializerMethodField()
    lesson_count = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail_url",
            "cover_image_url",
            "price_egp",
            "is_published",
            "module_count",
            "lesson_count",
            "modules",
            "created_at",
            "updated_at",
        ]

    def get_module_count(self, obj: Course) -> int:
        return obj.modules.count()

    def get_lesson_count(self, obj: Course) -> int:
        return Lesson.objects.filter(module__course=obj).count()

    def get_thumbnail_url(self, obj: Course) -> str | None:
        if obj.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
        return None

    def get_cover_image_url(self, obj: Course) -> str | None:
        if obj.cover_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
        return None


# ─────────────────────────────────────────────────────────────
# LessonProgress serializer
# ─────────────────────────────────────────────────────────────

class LessonProgressSerializer(serializers.ModelSerializer):
    """
    Handles reporting and updating a user's watch position.

    The client POSTs { lesson, last_watched_second } every 10 seconds
    during playback.  The server auto-calculates is_completed.
    """

    lesson_id = serializers.UUIDField(source="lesson.id", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)

    class Meta:
        model = LessonProgress
        fields = [
            "id",
            "lesson_id",
            "lesson_title",
            "last_watched_second",
            "is_completed",
            "updated_at",
        ]
        read_only_fields = ["is_completed", "updated_at"]

    def validate_last_watched_second(self, value: int) -> int:
        """Ensure the reported position is non-negative."""
        if value < 0:
            raise serializers.ValidationError(
                "Watch position cannot be negative."
            )
        return value

    def update(self, instance: LessonProgress, validated_data: dict) -> LessonProgress:
        """
        On update, also check if the lesson should be auto-marked complete.
        """
        instance.last_watched_second = validated_data.get(
            "last_watched_second", instance.last_watched_second
        )
        instance.save()
        # Attempt auto-completion check
        instance.mark_completed(threshold_percent=90.0)
        return instance


class LessonProgressReportSerializer(serializers.Serializer):
    """
    Write-only serializer for incoming progress reports from the player.

    Expected JSON body:
        { "lesson_id": "<uuid>", "last_watched_second": 42 }
    """

    lesson_id = serializers.UUIDField()
    last_watched_second = serializers.IntegerField(min_value=0)


# ─────────────────────────────────────────────────────────────
# VideoSession serializer
# ─────────────────────────────────────────────────────────────

class VideoSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for video playback sessions.
    Used for admin/debugging and session listing.
    """

    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    course_title = serializers.CharField(source="lesson.module.course.title", read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = VideoSession
        fields = [
            "id",
            "token",
            "lesson_title",
            "course_title",
            "expires_at",
            "is_revoked",
            "is_valid",
            "created_at",
        ]
        read_only_fields = [
            "id", "token", "lesson_title", "course_title",
            "expires_at", "is_valid", "created_at",
        ]


# ─────────────────────────────────────────────────────────────
# Enrollment serializer
# ─────────────────────────────────────────────────────────────

class EnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for user course enrollments.
    """
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source="course"
    )
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    course_thumbnail_url = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "course_id",
            "course_title",
            "course_slug",
            "course_thumbnail_url",
            "progress_percent",
            "enrolled_at",
        ]
        read_only_fields = ["id", "enrolled_at", "course_title", "course_slug", "course_thumbnail_url", "progress_percent"]

    def get_course_thumbnail_url(self, obj: Enrollment) -> str | None:
        if obj.course.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.course.thumbnail.url)
            return obj.course.thumbnail.url
        return None

    def get_progress_percent(self, obj: Enrollment) -> float:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0.0
        
        # Calculate progress
        lessons = Lesson.objects.filter(module__course=obj.course)
        total_lessons = lessons.count()
        if total_lessons == 0:
            return 0.0
            
        completed_lessons = LessonProgress.objects.filter(
            user=request.user,
            lesson__in=lessons,
            is_completed=True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100.0, 1)


# ─────────────────────────────────────────────────────────────
# Summary serializer (public, read-only)
# ─────────────────────────────────────────────────────────────

class SummaryListSerializer(serializers.ModelSerializer):
    """
    Public read-only serializer for published summaries.
    Provides file URL, display name, and source reference.
    """

    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = Summary
        fields = [
            "id",
            "title",
            "description",
            "file_url",
            "file_name",
            "file_size_display",
            "source",
            "source_url",
            "subject",
            "download_count",
            "created_at",
        ]

    def get_file_url(self, obj: Summary) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_file_name(self, obj: Summary) -> str:
        return obj.file_name

    def get_file_size_display(self, obj: Summary) -> str:
        size = obj.file_size_bytes
        if size == 0:
            return "0 B"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


# ─────────────────────────────────────────────────────────────
# Metadata (public)
# ─────────────────────────────────────────────────────────────

class PublicMetadataSerializer(serializers.ModelSerializer):
    """Public read-only serializer for published metadata entries."""

    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = MetadataEntry
        fields = [
            "id", "title", "description", "category",
            "source", "source_url",
            "file_url", "file_name", "file_size_display",
            "created_at",
        ]

    def get_file_url(self, obj) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_file_name(self, obj) -> str:
        return obj.file_name

    def get_file_size_display(self, obj) -> str:
        size = obj.file_size_bytes
        if size == 0:
            return "0 B"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


# ─────────────────────────────────────────────────────────────
# Spatial Data (public)
# ─────────────────────────────────────────────────────────────

class PublicSpatialDataSerializer(serializers.ModelSerializer):
    """Public read-only serializer for published spatial data entries."""

    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()
    data_type_display = serializers.SerializerMethodField()

    class Meta:
        model = SpatialDataEntry
        fields = [
            "id", "title", "description",
            "latitude", "longitude", "data_type", "data_type_display",
            "category", "source", "source_url",
            "file_url", "file_name", "file_size_display",
            "geojson_data",
            "created_at",
        ]

    def get_file_url(self, obj) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_file_name(self, obj) -> str:
        return obj.file_name

    def get_file_size_display(self, obj) -> str:
        size = obj.file_size_bytes
        if size == 0:
            return "0 B"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def get_data_type_display(self, obj) -> str:
        return obj.get_data_type_display()
