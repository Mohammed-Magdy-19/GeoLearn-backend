"""
apps/courses/secure_video_service.py

Secure Video Subsystem service layer.

Handles:
  • Session token generation and validation
  • Secure video metadata retrieval
  • Blob stream delivery with access control
  • Integration with the React frontend's secure player

The Secure Video Subsystem uses:
  • Short-lived session tokens (X-Playback-Token header)
  • Blob URL shielding (no direct video URLs exposed)
  • UUID-based video references (not URLs)
  • Automatic token revocation on logout/timeout

Environment variables required:
    SECURE_VIDEO_TOKEN_SECRET — Secret key for signing session tokens
    SECURE_VIDEO_STREAM_PATH  — Path to encrypted video storage
"""

import hashlib
import hmac
import base64
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponseForbidden, HttpResponseNotFound
from django.utils import timezone as django_timezone

from .models import Lesson, VideoSession


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

def get_secure_video_config() -> dict:
    """
    Read Secure Video Subsystem configuration from Django settings.
    """
    return {
        "token_secret": getattr(
            settings, "SECURE_VIDEO_TOKEN_SECRET", settings.SECRET_KEY
        ),
        "stream_path": getattr(
            settings, "SECURE_VIDEO_STREAM_PATH", "secure_videos/"
        ),
        "token_ttl_hours": getattr(
            settings, "SECURE_VIDEO_TOKEN_TTL_HOURS", 2
        ),
        "max_sessions_per_user": getattr(
            settings, "SECURE_VIDEO_MAX_SESSIONS", 5
        ),
    }


# ─────────────────────────────────────────────────────────────
# Session Token Management
# ─────────────────────────────────────────────────────────────

def generate_session_token() -> str:
    """
    Generate a cryptographically secure random session token.
    Returns a URL-safe base64-encoded string.
    """
    token_bytes = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")


def create_video_session(user, lesson: Lesson) -> VideoSession:
    """
    Create a new playback session for a user and lesson.

    Enforces max session limits per user (revokes oldest if exceeded).
    Returns the created VideoSession instance.
    """
    config = get_secure_video_config()

    # Enforce session limit: revoke oldest sessions if exceeded
    existing_sessions = VideoSession.objects.filter(
        user=user,
        is_revoked=False,
        expires_at__gt=django_timezone.now(),
    ).order_by("created_at")

    if existing_sessions.count() >= config["max_sessions_per_user"]:
        # Revoke oldest session to make room
        oldest = existing_sessions.first()
        if oldest:
            oldest.is_revoked = True
            oldest.save(update_fields=["is_revoked", "updated_at"])

    # Create new session
    expires_at = django_timezone.now() + timedelta(hours=config["token_ttl_hours"])
    token = generate_session_token()

    session, _ = VideoSession.objects.update_or_create(
        user=user,
        lesson=lesson,
        defaults={
            "token": token,
            "expires_at": expires_at,
            "is_revoked": False,
        },
    )

    return session


def validate_session_token(token: str) -> VideoSession | None:
    """
    Validate a session token and return the associated VideoSession.
    Returns None if token is invalid, expired, or revoked.
    """
    try:
        session = VideoSession.objects.select_related(
            "lesson", "lesson__module", "lesson__module__course", "user"
        ).get(token=token, is_revoked=False)
    except VideoSession.DoesNotExist:
        return None

    if not session.is_valid():
        return None

    return session


def revoke_session(token: str) -> bool:
    """
    Revoke a session token (e.g., on user logout).
    Returns True if a session was found and revoked.
    """
    try:
        session = VideoSession.objects.get(token=token, is_revoked=False)
        session.is_revoked = True
        session.save(update_fields=["is_revoked", "updated_at"])
        return True
    except VideoSession.DoesNotExist:
        return False


def revoke_all_user_sessions(user) -> int:
    """
    Revoke all active video sessions for a user.
    Returns the number of sessions revoked.
    """
    sessions = VideoSession.objects.filter(user=user, is_revoked=False)
    count = sessions.count()
    sessions.update(is_revoked=True)
    return count


# ─────────────────────────────────────────────────────────────
# Video Metadata Service
# ─────────────────────────────────────────────────────────────

def get_video_metadata(lesson: Lesson) -> dict:
    """
    Retrieve metadata for a secure video lesson.

    Returns a dict compatible with the frontend's VideoMetadata interface:
        { id, title, thumbnail, duration_seconds, is_free_preview }
    """
    if not lesson.has_video:
        return {
            "id": str(lesson.id),
            "title": lesson.title,
            "thumbnail": None,
            "duration_seconds": 0,
            "is_free_preview": lesson.is_free_preview,
            "has_video": False,
        }

    # Build thumbnail URL if available
    thumbnail_url = None
    course = lesson.module.course
    if course.thumbnail:
        # In a real implementation, this would be built via request context
        thumbnail_url = course.thumbnail.url

    return {
        "id": str(lesson.secure_video_id),
        "title": lesson.title,
        "thumbnail": thumbnail_url,
        "duration_seconds": lesson.duration_seconds,
        "is_free_preview": lesson.is_free_preview,
        "has_video": True,
    }


# ─────────────────────────────────────────────────────────────
# Secure Stream Delivery
# ─────────────────────────────────────────────────────────────

def get_video_file_path(secure_video_id: uuid.UUID) -> Path | None:
    """
    Resolve the physical file path for a secure video.

    In production, this would interface with encrypted storage.
    For development, it looks in the configured stream path.
    """
    config = get_secure_video_config()
    stream_path = Path(config["stream_path"])

    # Look for video file with secure_video_id as filename
    # Supports multiple formats: mp4, webm, mkv
    for ext in [".mp4", ".webm", ".mkv"]:
        file_path = stream_path / f"{secure_video_id}{ext}"
        if file_path.exists():
            return file_path

    return None


def serve_secure_stream(secure_video_id: uuid.UUID, request) -> FileResponse | HttpResponseNotFound:
    """
    Serve a video file as a secure stream response.

    Returns a FileResponse with headers that prevent caching and
    discourage direct downloading. The file is served as a blob
    to the frontend's secure player.

    Security headers applied:
      • Cache-Control: no-store, no-cache, must-revalidate
      • Content-Disposition: inline (not attachment)
      • X-Content-Type-Options: nosniff
    """
    file_path = get_video_file_path(secure_video_id)

    if not file_path:
        return HttpResponseNotFound("Video file not found.")

    # Determine content type based on extension
    content_type_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }
    content_type = content_type_map.get(file_path.suffix.lower(), "application/octet-stream")

    response = FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
        as_attachment=False,  # Inline playback, not download
    )

    # Security headers to prevent caching and extraction
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"

    return response


# ─────────────────────────────────────────────────────────────
# Access Control Helpers
# ─────────────────────────────────────────────────────────────

def check_lesson_access(user, lesson: Lesson) -> bool:
    """
    Determine if a user can access a lesson's video content.

    Access rules:
      • Free preview lessons: any authenticated user
      • Paid lessons: user must have purchased the course OR be staff
      • Free courses (price == 0): any authenticated user
    """
    if not user or not user.is_authenticated:
        return False

    # Staff always has access
    if user.is_staff or user.is_superuser:
        return True

    # Free preview lessons are accessible to all authenticated users
    if lesson.is_free_preview:
        return True

    course = lesson.module.course

    # Free courses are accessible to all authenticated users
    if course.price_egp == 0:
        return True

    # TODO(Phase 3): Check PaymentTransaction for actual purchase
    # from apps.payments.models import PaymentTransaction
    # return PaymentTransaction.objects.filter(
    #     user=user, course=course, status="SUCCESS"
    # ).exists()

    return False  # Conservative default — deny until payments are wired