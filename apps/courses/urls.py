"""
apps/courses/urls.py

URL routing for the courses app.

All routes are namespaced under /api/courses/ via the root config.urls.py.
Secure Video Subsystem routes are under /api/v1/videos/.

Available endpoints:
    GET    /                       — List published courses
    GET    /<slug>/                — Course detail with modules & lessons
    GET    /<slug>/lessons/<id>/   — Lesson detail + secure video metadata + session token
    GET    /<slug>/modules/<id>/lessons/ — Lessons in a module
    POST   /progress/              — Report watch position
    GET    /progress/              — List user's progress
    GET    /continue/              — Get "continue learning" lesson
    GET    /sessions/              — List active video sessions
    POST   /sessions/revoke/       — Revoke session(s)

Secure Video Subsystem:
    GET    /api/v1/videos/<video_id>/meta   — Video metadata
    GET    /api/v1/videos/<video_id>/stream  — Secure blob stream (X-Playback-Token)
"""

from django.urls import path

from . import views

urlpatterns = [
    # ── Course catalog ────────────────────────────────────────
    path(
        "",
        views.CourseListView.as_view(),
        name="course-list",
    ),

    # ── Enrollments ───────────────────────────────────────────
    path(
        "enroll/",
        views.EnrollView.as_view(),
        name="enroll",
    ),
    path(
        "my-enrollments/",
        views.MyEnrollmentsView.as_view(),
        name="my-enrollments",
    ),

    # ── Progress tracking ─────────────────────────────────────
    path(
        "progress/",
        views.LessonProgressReportView.as_view(),
        name="progress-report",
    ),
    path(
        "progress/list/",
        views.LessonProgressListView.as_view(),
        name="progress-list",
    ),

    # ── Continue learning ─────────────────────────────────────
    path(
        "continue/",
        views.ContinueLearningView.as_view(),
        name="continue-learning",
    ),

    # ── Session management ────────────────────────────────────
    path(
        "sessions/",
        views.VideoSessionListView.as_view(),
        name="session-list",
    ),
    path(
        "sessions/revoke/",
        views.VideoSessionRevokeView.as_view(),
        name="session-revoke",
    ),

    # ── Secure Video Subsystem (v1) ───────────────────────────
    path(
        "videos/<str:video_id>/meta/",
        views.VideoMetadataView.as_view(),
        name="video-metadata",
    ),
    path(
        "videos/<str:video_id>/stream/",
        views.VideoStreamView.as_view(),
        name="video-stream",
    ),

    # ── Course progress view ──
    path(
        "<uuid:course_id>/progress/",
        views.CourseProgressView.as_view(),
        name="course-progress",
    ),

    # ── Summaries (public, authenticated) ───────────────────────
    path(
        "summaries/",
        views.SummaryListView.as_view(),
        name="summary-list",
    ),
    path(
        "summaries/<str:summary_id>/download/",
        views.SummaryDownloadView.as_view(),
        name="summary-download",
    ),

    # ── Metadata (public, authenticated) ──────────────────────
    path(
        "metadata/",
        views.MetadataListView.as_view(),
        name="metadata-list",
    ),

    # ── Spatial Data (public, authenticated) ──────────────────
    path(
        "spatial-data/",
        views.SpatialDataListView.as_view(),
        name="spatial-data-list",
    ),

    # ── Course detail (placed at bottom to prevent slug collisions) ──
    path(
        "<slug:slug>/",
        views.CourseDetailView.as_view(),
        name="course-detail",
    ),

    # ── Lesson playback ───────────────────────────────────────
    path(
        "<slug:slug>/lessons/<str:lesson_id>/",
        views.LessonDetailView.as_view(),
        name="lesson-detail",
    ),

    # ── Module lesson list (sidebar navigation) ───────────────
    path(
        "<slug:slug>/modules/<str:module_id>/lessons/",
        views.ModuleLessonListView.as_view(),
        name="module-lesson-list",
    ),
]