"""
apps/courses/admin.py

Django Admin configuration for course content management.

Provides inline editing of lessons within modules, and modules
within courses, so content creators can build curricula without
leaving the admin interface.
"""

from django.contrib import admin

from .models import Course, Module, Lesson, LessonProgress, VideoSession, Enrollment


# ─────────────────────────────────────────────────────────────
# Inlines
# ─────────────────────────────────────────────────────────────

class LessonInline(admin.TabularInline):
    """
    Inline lesson editor inside the Module admin page.
    Allows quick reordering and editing of lessons.
    """

    model = Lesson
    extra = 1
    fields = ["title", "order_index", "duration_seconds", "is_free_preview", "secure_video_id"]
    ordering = ["order_index"]
    show_change_link = True


class ModuleInline(admin.StackedInline):
    """
    Inline module editor inside the Course admin page.
    Shows module details and nested lessons.
    """

    model = Module
    extra = 1
    fields = ["title", "description", "order_index"]
    ordering = ["order_index"]
    show_change_link = True
    inlines = [LessonInline]  # Django doesn't support nested inlines natively,
                               # but we register ModuleAdmin separately below.


# ─────────────────────────────────────────────────────────────
# ModelAdmin classes
# ─────────────────────────────────────────────────────────────

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """
    Admin interface for managing courses.
    """

    list_display = [
        "title",
        "slug",
        "price_egp",
        "is_published",
        "module_count_display",
        "created_at",
    ]
    list_filter = ["is_published", "created_at"]
    search_fields = ["title", "slug", "description"]
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "created_at"
    inlines = [ModuleInline]

    fieldsets = (
        ("Basic Info", {
            "fields": ("title", "slug", "description"),
        }),
        ("Visual Assets", {
            "fields": ("thumbnail", "cover_image"),
        }),
        ("Pricing & Access", {
            "fields": ("price_egp", "is_published"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ["created_at", "updated_at"]

    def module_count_display(self, obj: Course) -> int:
        return obj.modules.count()
    module_count_display.short_description = "Modules"


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """
    Admin interface for managing modules.
    Includes inline lesson editing.
    """

    list_display = [
        "title",
        "course",
        "order_index",
        "lesson_count_display",
    ]
    list_filter = ["course"]
    search_fields = ["title", "course__title"]
    ordering = ["course", "order_index"]
    inlines = [LessonInline]

    def lesson_count_display(self, obj: Module) -> int:
        return obj.lessons.count()
    lesson_count_display.short_description = "Lessons"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    """
    Admin interface for managing individual lessons.
    """

    list_display = [
        "title",
        "module",
        "order_index",
        "duration_display",
        "is_free_preview",
        "has_video",
    ]
    list_filter = ["module__course", "is_free_preview"]
    search_fields = ["title", "secure_video_id"]
    ordering = ["module", "order_index"]

    fieldsets = (
        ("Basic Info", {
            "fields": ("module", "title", "description"),
        }),
        ("Ordering", {
            "fields": ("order_index",),
        }),
        ("Video", {
            "fields": ("secure_video_id", "duration_seconds"),
            "description": (
                "secure_video_id: The Secure Video Subsystem UUID reference. "
                "Upload the video to the secure storage and paste its UUID here."
            ),
        }),
        ("Access", {
            "fields": ("is_free_preview",),
            "description": (
                "Free preview lessons are watchable without purchasing the course."
            ),
        }),
    )

    def duration_display(self, obj: Lesson) -> str:
        minutes, seconds = divmod(obj.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
    duration_display.short_description = "Duration"

    def has_video(self, obj: Lesson) -> bool:
        return obj.has_video
    has_video.boolean = True
    has_video.short_description = "Has Video"


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing student progress.
    Read-only to prevent accidental data manipulation.
    """

    list_display = [
        "user",
        "lesson",
        "last_watched_second",
        "is_completed",
        "updated_at",
    ]
    list_filter = ["is_completed", "updated_at"]
    search_fields = [
        "user__phone_number",
        "user__full_name",
        "lesson__title",
    ]
    ordering = ["-updated_at"]
    date_hierarchy = "updated_at"

    # Read-only to prevent admin from accidentally changing progress
    readonly_fields = [
        "user",
        "lesson",
        "last_watched_second",
        "is_completed",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request) -> bool:
        """Progress records are created automatically by the API."""
        return False


@admin.register(VideoSession)
class VideoSessionAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing video playback sessions.
    Read-only to prevent token manipulation.
    """

    list_display = [
        "user",
        "lesson",
        "token_short",
        "expires_at",
        "is_revoked",
        "is_valid",
        "created_at",
    ]
    list_filter = ["is_revoked", "expires_at", "created_at"]
    search_fields = [
        "user__phone_number",
        "user__full_name",
        "lesson__title",
        "token",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    readonly_fields = [
        "user",
        "lesson",
        "token",
        "expires_at",
        "is_revoked",
        "created_at",
        "updated_at",
    ]

    def token_short(self, obj: VideoSession) -> str:
        return obj.token[:16] + "..." if len(obj.token) > 16 else obj.token
    token_short.short_description = "Token"

    def is_valid(self, obj: VideoSession) -> bool:
        return obj.is_valid()
    is_valid.boolean = True
    is_valid.short_description = "Valid"

    def has_add_permission(self, request) -> bool:
        """Sessions are created automatically by the API."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Sessions should not be manually modified."""
        return False


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["user", "course", "enrolled_at"]
    list_filter = ["enrolled_at", "course"]
    search_fields = ["user__username", "user__full_name", "course__title"]
    readonly_fields = ["enrolled_at"]