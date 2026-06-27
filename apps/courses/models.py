"""
apps/courses/models.py

Relational database schemas for the course content hierarchy.

Hierarchy:
    Course (1) -> (*) Module (1) -> (*) Lesson

Each Lesson represents a single video unit served via the Secure Video Subsystem.
LessonProgress tracks per-user viewing state for resume-playback support.
"""

import uuid
from django.db import models
from django.conf import settings


# ─────────────────────────────────────────────────────────────
# Course
# ─────────────────────────────────────────────────────────────

class Course(models.Model):
    """
    Top-level learning product.

    A Course is a purchasable unit that contains an ordered sequence
    of Modules, each containing Lessons.  The `is_published` flag
    allows drafting content before it becomes visible to students.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=280)
    description = models.TextField(blank=True)

    # Visual assets
    thumbnail = models.ImageField(
        upload_to="courses/thumbnails/%Y/%m/",
        blank=True,
        null=True,
        help_text="Square-ish thumbnail shown in the course catalog",
    )
    cover_image = models.ImageField(
        upload_to="courses/covers/%Y/%m/",
        blank=True,
        null=True,
        help_text="Wide banner image for the course detail page",
    )

    # Pricing (EGP)
    price_egp = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Set to 0.00 for free courses",
    )

    # Lifecycle
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "courses"
        ordering = ["-created_at"]
        verbose_name = "Course"
        verbose_name_plural = "Courses"

    def __str__(self) -> str:
        return self.title


# ─────────────────────────────────────────────────────────────
# Module
# ─────────────────────────────────────────────────────────────

class Module(models.Model):
    """
    A thematic chapter inside a Course.

    Modules group related lessons together (e.g. "Week 1: Introduction").
    The `order_index` field controls display sequence.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="modules",
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order_index = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order within the parent course (0 = first)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "modules"
        ordering = ["course", "order_index"]
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        # Prevent duplicate order indices within the same course
        constraints = [
            models.UniqueConstraint(
                fields=["course", "order_index"],
                name="unique_module_order_per_course",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} / {self.title}"


# ─────────────────────────────────────────────────────────────
# Lesson
# ─────────────────────────────────────────────────────────────

class Lesson(models.Model):
    """
    A single video lesson inside a Module.

    The `secure_video_id` stores the UUID reference to the Secure Video Subsystem.
    This is NOT a URL — the frontend requests blob streams via the API layer.
    `duration_seconds` is cached after video processing so the UI can show
    lesson length without fetching the actual video.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="lessons",
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order_index = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order within the parent module (0 = first)",
    )

    # Secure Video Subsystem — stored as UUID reference, not a URL
    secure_video_id = models.UUIDField(
        blank=True,
        null=True,
        help_text="Secure Video Subsystem video UUID (not a URL). "
                   "The frontend fetches blob streams via /api/v1/videos/{id}/stream",
    )
    duration_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Cached video duration in seconds (0 = unknown)",
    )

    # Free preview — allow non-purchasers to watch this lesson
    is_free_preview = models.BooleanField(
        default=False,
        help_text="If True, this lesson is watchable without purchase",
    )
    lesson_file = models.FileField(
        upload_to="lessons/files/%Y/%m/",
        blank=True,
        null=True,
        help_text="Supplemental materials for the lesson (e.g. PDF)",
        verbose_name="Lesson File",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lessons"
        ordering = ["module", "order_index"]
        verbose_name = "Lesson"
        verbose_name_plural = "Lessons"
        constraints = [
            models.UniqueConstraint(
                fields=["module", "order_index"],
                name="unique_lesson_order_per_module",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.module.title} / {self.title}"

    @property
    def has_video(self) -> bool:
        """Check if this lesson has an associated secure video."""
        return self.secure_video_id is not None


# ─────────────────────────────────────────────────────────────
# VideoSession — Secure playback session tokens
# ─────────────────────────────────────────────────────────────

class VideoSession(models.Model):
    """
    Short-lived playback session for secure video streaming.

    The Secure Video Subsystem issues session tokens tied to a specific
    user and lesson. Tokens expire after a short duration (default 2 hours)
    and are required in the X-Playback-Token header for stream requests.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="video_sessions",
        db_index=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="video_sessions",
        db_index=True,
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_revoked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_sessions"
        ordering = ["-created_at"]
        verbose_name = "Video Session"
        verbose_name_plural = "Video Sessions"
        # One active session per (user, lesson) pair at a time
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lesson"],
                name="unique_session_per_user_lesson",
            ),
        ]

    def __str__(self) -> str:
        return f"Session {self.token[:16]}... for {self.user}"

    def is_valid(self) -> bool:
        """Check if the session token is still valid (not expired or revoked)."""
        from django.utils import timezone
        return not self.is_revoked and self.expires_at > timezone.now()


# ─────────────────────────────────────────────────────────────
# LessonProgress — Student viewing ledger
# ─────────────────────────────────────────────────────────────

class LessonProgress(models.Model):
    """
    Per-user, per-lesson playback tracking.

    `last_watched_second` is the farthest timestamp the student has
    reached (used for resume-playback).  `is_completed` flips to
    True once the student watches >= 90 % of the lesson duration.

    updated_at is indexed because the "continue learning" API
    sorts by it to surface the most recently active lesson.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_progresses",
        db_index=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="progress_entries",
        db_index=True,
    )
    last_watched_second = models.PositiveIntegerField(
        default=0,
        help_text="Farthest playback position reached in seconds",
    )
    is_completed = models.BooleanField(
        default=False,
        help_text="True when the student has watched >= 90 % of the lesson",
    )

    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lesson_progress"
        # One progress record per (user, lesson) pair
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lesson"],
                name="unique_progress_per_user_lesson",
            ),
        ]
        verbose_name = "Lesson Progress"
        verbose_name_plural = "Lesson Progresses"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.lesson} ({self.last_watched_second}s)"

    def mark_completed(self, threshold_percent: float = 90.0) -> bool:
        """
        Check if the lesson should be marked completed based on
        the current watch position and lesson duration.
        Returns True if the completion state changed.
        """
        if self.is_completed:
            return False

        duration = self.lesson.duration_seconds
        if duration == 0:
            return False

        watched_pct = (self.last_watched_second / duration) * 100
        if watched_pct >= threshold_percent:
            self.is_completed = True
            self.save(update_fields=["is_completed", "updated_at"])
            return True
        return False


# ─────────────────────────────────────────────────────────────
# Enrollment
# ─────────────────────────────────────────────────────────────

class Enrollment(models.Model):
    """
    Tracks which courses a student is enrolled in.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        db_index=True,
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
        db_index=True,
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "enrollments"
        ordering = ["-enrolled_at"]
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="unique_enrollment_per_user_course",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} enrolled in {self.course.title}"


# ─────────────────────────────────────────────────────────────
# Summary — Downloadable study resources
# ─────────────────────────────────────────────────────────────

class Summary(models.Model):
    """
    A downloadable study resource (PDF, document, map, etc.).

    Summaries are organized by subject and include an optional source
    reference. Admin can upload files via the dashboard and control
    visibility with the `is_published` flag.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(
        max_length=255,
        help_text="Display title shown to students",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description or notes about the summary",
    )
    file = models.FileField(
        upload_to="summaries/%Y/%m/",
        help_text="The downloadable file (PDF, DOCX, etc.)",
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the reference or source (e.g. كتاب الخرائط)",
    )
    source_url = models.URLField(
        blank=True,
        help_text="Optional URL link to the source/reference",
    )
    subject = models.CharField(
        max_length=100,
        blank=True,
        help_text="Subject or topic (e.g. خرائط, جيولوجيا)",
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Only published summaries are visible to students",
    )
    download_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this file has been downloaded",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "summaries"
        ordering = ["-created_at"]
        verbose_name = "Summary"
        verbose_name_plural = "Summaries"

    def __str__(self) -> str:
        return self.title

    @property
    def file_size_bytes(self) -> int:
        """Return the file size in bytes, or 0 if no file."""
        try:
            return self.file.size
        except (FileNotFoundError, ValueError):
            return 0

    @property
    def file_name(self) -> str:
        """Return the original filename from the upload path."""
        import os
        return os.path.basename(self.file.name) if self.file else ""


# ─────────────────────────────────────────────────────────────
# Metadata Entries
# ─────────────────────────────────────────────────────────────

class MetadataEntry(models.Model):
    """
    Structured descriptive metadata entry.

    Used to publish reference data such as data dictionaries,
    attribute descriptions, and documentation resources.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(
        max_length=255,
        help_text="Display title for this metadata entry",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the metadata",
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="Category or type (e.g. بيانات جغرافية, بيانات سكانية)",
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the reference or source",
    )
    source_url = models.URLField(
        blank=True,
        help_text="Optional URL link to the source",
    )
    file = models.FileField(
        upload_to="metadata/%Y/%m/",
        blank=True,
        help_text="Optional attached file (PDF, DOCX, etc.)",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Only published entries are visible publicly",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "metadata_entries"
        ordering = ["-created_at"]
        verbose_name = "Metadata Entry"
        verbose_name_plural = "Metadata Entries"

    def __str__(self) -> str:
        return self.title

    @property
    def file_size_bytes(self) -> int:
        try:
            return self.file.size if self.file else 0
        except (FileNotFoundError, ValueError):
            return 0

    @property
    def file_name(self) -> str:
        import os
        return os.path.basename(self.file.name) if self.file else ""


# ─────────────────────────────────────────────────────────────
# Spatial Data Entries
# ─────────────────────────────────────────────────────────────

class SpatialDataEntry(models.Model):
    """
    Spatial/GIS data entry with coordinates for map display.

    Each entry has a geographic location (lat/lng) and optionally
    includes GeoJSON data for rendering shapes on the map.
    Files such as Shapefiles, KML, or GeoJSON can be attached.
    """

    DATA_TYPE_CHOICES = [
        ("point", "نقطة"),
        ("line", "خط"),
        ("polygon", "مضلع"),
        ("layer", "طبقة"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(
        max_length=255,
        help_text="Display title for this spatial data entry",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the spatial data",
    )
    latitude = models.FloatField(
        help_text="Latitude coordinate (e.g. 30.0444 for Cairo)",
    )
    longitude = models.FloatField(
        help_text="Longitude coordinate (e.g. 31.2357 for Cairo)",
    )
    data_type = models.CharField(
        max_length=50,
        choices=DATA_TYPE_CHOICES,
        default="point",
        help_text="Type of spatial data",
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text="Category (e.g. مواقع أثرية, حدود إدارية)",
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the reference or source",
    )
    source_url = models.URLField(
        blank=True,
        help_text="Optional URL link to the source",
    )
    file = models.FileField(
        upload_to="spatial/%Y/%m/",
        blank=True,
        help_text="Optional spatial file (Shapefile, GeoJSON, KML, etc.)",
    )
    geojson_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Inline GeoJSON data for map rendering",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Only published entries are visible publicly",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spatial_data_entries"
        ordering = ["-created_at"]
        verbose_name = "Spatial Data Entry"
        verbose_name_plural = "Spatial Data Entries"

    def __str__(self) -> str:
        return f"{self.title} ({self.get_data_type_display()})"

    @property
    def file_size_bytes(self) -> int:
        try:
            return self.file.size if self.file else 0
        except (FileNotFoundError, ValueError):
            return 0

    @property
    def file_name(self) -> str:
        import os
        return os.path.basename(self.file.name) if self.file else ""
