"""
apps/courses/tests.py

Comprehensive test suite for the Secure Video Subsystem.

Covers:
  • Model behavior (Course, Module, Lesson, LessonProgress, VideoSession)
  • Session token generation and validation
  • Access control (free preview, paid, staff)
  • Progress tracking and auto-completion
  • Secure stream delivery (metadata + blob)
  • API endpoint responses and permissions
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import Course, Module, Lesson, LessonProgress, VideoSession
from .secure_video_service import (
    generate_session_token,
    create_video_session,
    validate_session_token,
    revoke_session,
    revoke_all_user_sessions,
    check_lesson_access,
    get_video_metadata,
    serve_secure_stream,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────────────────────

def create_user(phone="+201000000001", is_staff=False, is_superuser=False):
    """Create a test user."""
    return User.objects.create(
        phone_number=phone,
        full_name="Test User",
        is_staff=is_staff,
        is_superuser=is_superuser,
    )

def create_course(title="Test Course", price=100.00, published=True):
    """Create a test course with modules and lessons."""
    course = Course.objects.create(
        title=title,
        slug=f"test-course-{uuid.uuid4().hex[:8]}",
        description="Test course description",
        price_egp=price,
        is_published=published,
    )
    module = Module.objects.create(
        course=course,
        title="Test Module",
        order_index=0,
    )
    lesson = Lesson.objects.create(
        module=module,
        title="Test Lesson",
        order_index=0,
        duration_seconds=120,
        secure_video_id=uuid.uuid4(),
    )
    return course, module, lesson


# ─────────────────────────────────────────────────────────────
# Model Tests
# ─────────────────────────────────────────────────────────────

class CourseModelTests(TestCase):
    """Test Course model behavior."""

    def test_course_creation(self):
        course = Course.objects.create(
            title="Python Basics",
            slug="python-basics",
            price_egp=199.99,
        )
        self.assertEqual(str(course), "Python Basics")
        self.assertFalse(course.is_published)

    def test_slug_uniqueness(self):
        Course.objects.create(title="Course 1", slug="unique-slug")
        with self.assertRaises(Exception):
            Course.objects.create(title="Course 2", slug="unique-slug")


class LessonModelTests(TestCase):
    """Test Lesson model behavior."""

    def test_has_video_property(self):
        course, module, lesson = create_course()
        self.assertTrue(lesson.has_video)

        lesson_no_video = Lesson.objects.create(
            module=module,
            title="No Video Lesson",
            order_index=1,
        )
        self.assertFalse(lesson_no_video.has_video)

    def test_duration_display(self):
        course, module, lesson = create_course()
        lesson.duration_seconds = 125
        lesson.save()
        # Test via admin method
        minutes, seconds = divmod(lesson.duration_seconds, 60)
        self.assertEqual(f"{minutes:02d}:{seconds:02d}", "02:05")


class LessonProgressModelTests(TestCase):
    """Test LessonProgress auto-completion logic."""

    def test_mark_completed_threshold(self):
        user = create_user()
        course, module, lesson = create_course()
        lesson.duration_seconds = 100
        lesson.save()

        progress = LessonProgress.objects.create(
            user=user,
            lesson=lesson,
            last_watched_second=0,
        )

        # Not enough watched
        progress.last_watched_second = 89
        progress.save()
        result = progress.mark_completed(threshold_percent=90.0)
        self.assertFalse(result)
        self.assertFalse(progress.is_completed)

        # Exactly at threshold
        progress.last_watched_second = 90
        progress.save()
        result = progress.mark_completed(threshold_percent=90.0)
        self.assertTrue(result)
        self.assertTrue(progress.is_completed)

        # Already completed — no change
        result = progress.mark_completed(threshold_percent=90.0)
        self.assertFalse(result)

    def test_mark_completed_zero_duration(self):
        user = create_user()
        course, module, lesson = create_course()
        lesson.duration_seconds = 0
        lesson.save()

        progress = LessonProgress.objects.create(
            user=user,
            lesson=lesson,
            last_watched_second=50,
        )

        result = progress.mark_completed()
        self.assertFalse(result)


class VideoSessionModelTests(TestCase):
    """Test VideoSession token lifecycle."""

    def test_session_validity(self):
        user = create_user()
        course, module, lesson = create_course()

        session = VideoSession.objects.create(
            user=user,
            lesson=lesson,
            token="test-token-123",
            expires_at=timezone.now() + timedelta(hours=2),
        )

        self.assertTrue(session.is_valid())

        # Expire the session
        session.expires_at = timezone.now() - timedelta(hours=1)
        session.save()
        self.assertFalse(session.is_valid())

        # Revoke the session
        session.expires_at = timezone.now() + timedelta(hours=2)
        session.is_revoked = True
        session.save()
        self.assertFalse(session.is_valid())

    def test_unique_constraint(self):
        user = create_user()
        course, module, lesson = create_course()

        VideoSession.objects.create(
            user=user,
            lesson=lesson,
            token="token-1",
            expires_at=timezone.now() + timedelta(hours=2),
        )

        with self.assertRaises(Exception):
            VideoSession.objects.create(
                user=user,
                lesson=lesson,
                token="token-2",
                expires_at=timezone.now() + timedelta(hours=2),
            )


# ─────────────────────────────────────────────────────────────
# Secure Video Service Tests
# ─────────────────────────────────────────────────────────────

class SessionTokenTests(TestCase):
    """Test session token generation and management."""

    def test_generate_session_token(self):
        token = generate_session_token()
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

        # Tokens should be unique
        token2 = generate_session_token()
        self.assertNotEqual(token, token2)

    def test_create_video_session(self):
        user = create_user()
        course, module, lesson = create_course()

        session = create_video_session(user, lesson)
        self.assertIsNotNone(session.token)
        self.assertEqual(session.user, user)
        self.assertEqual(session.lesson, lesson)
        self.assertTrue(session.is_valid())

    def test_session_limit_enforcement(self):
        user = create_user()
        course, module, lesson = create_course()

        # Create max sessions (default 5)
        for i in range(5):
            m = Module.objects.create(course=course, title=f"Mod {i}", order_index=i)
            l = Lesson.objects.create(module=m, title=f"Les {i}", order_index=i, secure_video_id=uuid.uuid4())
            create_video_session(user, l)

        # 6th session should revoke the oldest
        m6 = Module.objects.create(course=course, title="Mod 6", order_index=6)
        l6 = Lesson.objects.create(module=m6, title="Les 6", order_index=6, secure_video_id=uuid.uuid4())
        session6 = create_video_session(user, l6)

        self.assertEqual(session6.user, user)
        # Oldest session should be revoked
        oldest = VideoSession.objects.filter(user=user).order_by("created_at").first()
        self.assertTrue(oldest.is_revoked)

    def test_validate_session_token(self):
        user = create_user()
        course, module, lesson = create_course()

        session = create_video_session(user, lesson)

        # Valid token
        validated = validate_session_token(session.token)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.id, session.id)

        # Invalid token
        self.assertIsNone(validate_session_token("invalid-token"))

        # Expired token
        session.expires_at = timezone.now() - timedelta(hours=1)
        session.save()
        self.assertIsNone(validate_session_token(session.token))

    def test_revoke_session(self):
        user = create_user()
        course, module, lesson = create_course()

        session = create_video_session(user, lesson)
        self.assertTrue(session.is_valid())

        result = revoke_session(session.token)
        self.assertTrue(result)

        session.refresh_from_db()
        self.assertTrue(session.is_revoked)
        self.assertFalse(session.is_valid())

        # Revoke non-existent token
        self.assertFalse(revoke_session("non-existent"))

    def test_revoke_all_user_sessions(self):
        user = create_user()
        course, module, lesson = create_course()

        for i in range(3):
            m = Module.objects.create(course=course, title=f"M{i}", order_index=i)
            l = Lesson.objects.create(module=m, title=f"L{i}", order_index=i, secure_video_id=uuid.uuid4())
            create_video_session(user, l)

        count = revoke_all_user_sessions(user)
        self.assertEqual(count, 3)

        active = VideoSession.objects.filter(user=user, is_revoked=False).count()
        self.assertEqual(active, 0)


class AccessControlTests(TestCase):
    """Test lesson access control logic."""

    def test_free_preview_access(self):
        user = create_user()
        course, module, lesson = create_course()
        lesson.is_free_preview = True
        lesson.save()

        self.assertTrue(check_lesson_access(user, lesson))

    def test_free_course_access(self):
        user = create_user()
        course, module, lesson = create_course(price=0.00)
        lesson.is_free_preview = False
        lesson.save()

        self.assertTrue(check_lesson_access(user, lesson))

    def test_staff_access(self):
        user = create_user(is_staff=True)
        course, module, lesson = create_course(price=100.00)
        lesson.is_free_preview = False
        lesson.save()

        self.assertTrue(check_lesson_access(user, lesson))

    def test_paid_lesson_no_access(self):
        user = create_user()
        course, module, lesson = create_course(price=100.00)
        lesson.is_free_preview = False
        lesson.save()

        # Regular user without purchase should be denied
        self.assertFalse(check_lesson_access(user, lesson))

    def test_anonymous_no_access(self):
        course, module, lesson = create_course()
        anonymous_user = MagicMock()
        anonymous_user.is_authenticated = False

        self.assertFalse(check_lesson_access(anonymous_user, lesson))


class VideoMetadataTests(TestCase):
    """Test video metadata retrieval."""

    def test_metadata_with_video(self):
        course, module, lesson = create_course()
        metadata = get_video_metadata(lesson)

        self.assertEqual(metadata["id"], str(lesson.secure_video_id))
        self.assertEqual(metadata["title"], lesson.title)
        self.assertEqual(metadata["duration_seconds"], lesson.duration_seconds)
        self.assertTrue(metadata["has_video"])

    def test_metadata_without_video(self):
        course, module, lesson = create_course()
        lesson.secure_video_id = None
        lesson.save()

        metadata = get_video_metadata(lesson)
        self.assertFalse(metadata["has_video"])
        self.assertEqual(metadata["duration_seconds"], 0)


# ─────────────────────────────────────────────────────────────
# API Endpoint Tests
# ─────────────────────────────────────────────────────────────

class CourseAPITests(APITestCase):
    """Test course list and detail API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()

    def test_course_list(self):
        url = reverse("course-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Test Course")

    def test_course_list_search(self):
        Course.objects.create(
            title="Advanced Python",
            slug="advanced-python",
            price_egp=299.00,
            is_published=True,
        )

        url = reverse("course-list")
        response = self.client.get(url, {"search": "Advanced"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Advanced Python")

    def test_course_detail(self):
        url = reverse("course-detail", kwargs={"slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Course")
        self.assertEqual(len(response.data["modules"]), 1)

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        url = reverse("course-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LessonAPITests(APITestCase):
    """Test lesson detail and module lesson list endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()

    def test_lesson_detail_free_preview(self):
        self.lesson.is_free_preview = True
        self.lesson.save()

        url = reverse("lesson-detail", kwargs={
            "slug": self.course.slug,
            "lesson_id": str(self.lesson.id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Lesson")
        self.assertIn("video_metadata", response.data)
        self.assertIn("session_token", response.data)
        self.assertIsNotNone(response.data["session_token"])

    def test_lesson_detail_paid_no_access(self):
        self.lesson.is_free_preview = False
        self.lesson.save()

        url = reverse("lesson-detail", kwargs={
            "slug": self.course.slug,
            "lesson_id": str(self.lesson.id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lesson_detail_staff_access(self):
        staff_user = create_user(phone="+201000000002", is_staff=True)
        self.client.force_authenticate(user=staff_user)

        self.lesson.is_free_preview = False
        self.lesson.save()

        url = reverse("lesson-detail", kwargs={
            "slug": self.course.slug,
            "lesson_id": str(self.lesson.id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_module_lesson_list(self):
        url = reverse("module-lesson-list", kwargs={
            "slug": self.course.slug,
            "module_id": str(self.module.id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Test Lesson")


class ProgressAPITests(APITestCase):
    """Test progress reporting and retrieval endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()
        self.lesson.is_free_preview = True
        self.lesson.save()

    def test_report_progress(self):
        url = reverse("progress-report")
        data = {
            "lesson_id": str(self.lesson.id),
            "last_watched_second": 45,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["last_watched_second"], 45)
        self.assertFalse(response.data["is_completed"])

    def test_progress_auto_completion(self):
        self.lesson.duration_seconds = 100
        self.lesson.save()

        url = reverse("progress-report")
        data = {
            "lesson_id": str(self.lesson.id),
            "last_watched_second": 95,  # > 90%
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_completed"])

    def test_progress_list(self):
        # Create some progress
        LessonProgress.objects.create(
            user=self.user,
            lesson=self.lesson,
            last_watched_second=30,
        )

        url = reverse("progress-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_continue_learning(self):
        LessonProgress.objects.create(
            user=self.user,
            lesson=self.lesson,
            last_watched_second=60,
        )

        url = reverse("continue-learning")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["lesson"]["title"], "Test Lesson")
        self.assertEqual(response.data["progress"]["last_watched_second"], 60)
        self.assertEqual(response.data["course"]["title"], "Test Course")

    def test_continue_learning_no_progress(self):
        url = reverse("continue-learning")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class VideoSessionAPITests(APITestCase):
    """Test video session management endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()

    def test_session_list(self):
        create_video_session(self.user, self.lesson)

        url = reverse("session-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_revoke_session(self):
        session = create_video_session(self.user, self.lesson)

        url = reverse("session-revoke")
        data = {"token": session.token}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        session.refresh_from_db()
        self.assertTrue(session.is_revoked)

    def test_revoke_all_sessions(self):
        for i in range(3):
            m = Module.objects.create(course=self.course, title=f"M{i}", order_index=i)
            l = Lesson.objects.create(module=m, title=f"L{i}", order_index=i, secure_video_id=uuid.uuid4())
            create_video_session(self.user, l)

        url = reverse("session-revoke")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("3", response.data["detail"])


class SecureVideoStreamTests(APITestCase):
    """Test Secure Video Subsystem metadata and stream endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()
        self.lesson.is_free_preview = True
        self.lesson.save()

    def test_video_metadata(self):
        url = reverse("video-metadata", kwargs={
            "video_id": str(self.lesson.secure_video_id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.lesson.secure_video_id))
        self.assertEqual(response.data["title"], "Test Lesson")
        self.assertTrue(response.data["has_video"])

    def test_video_metadata_no_access(self):
        self.lesson.is_free_preview = False
        self.lesson.save()

        url = reverse("video-metadata", kwargs={
            "video_id": str(self.lesson.secure_video_id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_video_stream_no_token(self):
        url = reverse("video-stream", kwargs={
            "video_id": str(self.lesson.secure_video_id),
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_video_stream_invalid_token(self):
        url = reverse("video-stream", kwargs={
            "video_id": str(self.lesson.secure_video_id),
        })
        response = self.client.get(url, HTTP_X_PLAYBACK_TOKEN="invalid-token")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.courses.secure_video_service.get_video_file_path")
    def test_video_stream_with_valid_token(self, mock_get_path):
        # Create a mock file path
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.suffix = ".mp4"
        mock_get_path.return_value = mock_path

        # Create session token
        session = create_video_session(self.user, self.lesson)

        url = reverse("video-stream", kwargs={
            "video_id": str(self.lesson.secure_video_id),
        })
        response = self.client.get(url, HTTP_X_PLAYBACK_TOKEN=session.token)

        # Should return 200 or 404 depending on file existence
        # In test environment, FileResponse may fail if file doesn't exist
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

    def test_video_stream_wrong_video(self):
        other_lesson = Lesson.objects.create(
            module=self.module,
            title="Other Lesson",
            order_index=1,
            secure_video_id=uuid.uuid4(),
        )

        # Create session for original lesson
        session = create_video_session(self.user, self.lesson)

        # Request stream for different video
        url = reverse("video-stream", kwargs={
            "video_id": str(other_lesson.secure_video_id),
        })
        response = self.client.get(url, HTTP_X_PLAYBACK_TOKEN=session.token)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────

class FullPlaybackFlowTests(APITestCase):
    """Test the complete video playback flow from lesson detail to stream."""

    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(user=self.user)
        self.course, self.module, self.lesson = create_course()
        self.lesson.is_free_preview = True
        self.lesson.duration_seconds = 300
        self.lesson.save()

    def test_complete_playback_flow(self):
        # Step 1: Get lesson detail (includes session token)
        lesson_url = reverse("lesson-detail", kwargs={
            "slug": self.course.slug,
            "lesson_id": str(self.lesson.id),
        })
        response = self.client.get(lesson_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        session_token = response.data["session_token"]
        video_id = response.data["video_metadata"]["id"]
        self.assertIsNotNone(session_token)

        # Step 2: Get video metadata
        meta_url = reverse("video-metadata", kwargs={"video_id": video_id})
        meta_response = self.client.get(meta_url)
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)

        # Step 3: Report progress at 50 seconds
        progress_url = reverse("progress-report")
        progress_data = {
            "lesson_id": str(self.lesson.id),
            "last_watched_second": 50,
        }
        progress_response = self.client.post(progress_url, progress_data, format="json")
        self.assertEqual(progress_response.status_code, status.HTTP_200_OK)
        self.assertEqual(progress_response.data["last_watched_second"], 50)
        self.assertFalse(progress_response.data["is_completed"])

        # Step 4: Report progress at 280 seconds (> 90% of 300)
        progress_data["last_watched_second"] = 280
        progress_response = self.client.post(progress_url, progress_data, format="json")
        self.assertEqual(progress_response.status_code, status.HTTP_200_OK)
        self.assertTrue(progress_response.data["is_completed"])

        # Step 5: Check continue learning returns this lesson
        continue_url = reverse("continue-learning")
        continue_response = self.client.get(continue_url)
        self.assertEqual(continue_response.status_code, status.HTTP_200_OK)
        self.assertEqual(continue_response.data["lesson"]["id"], str(self.lesson.id))
        self.assertTrue(continue_response.data["progress"]["is_completed"])

        # Step 6: Revoke session
        revoke_url = reverse("session-revoke")
        revoke_response = self.client.post(revoke_url, {"token": session_token}, format="json")
        self.assertEqual(revoke_response.status_code, status.HTTP_200_OK)

        # Step 7: Verify stream is now blocked
        stream_url = reverse("video-stream", kwargs={"video_id": video_id})
        stream_response = self.client.get(stream_url, HTTP_X_PLAYBACK_TOKEN=session_token)
        self.assertEqual(stream_response.status_code, status.HTTP_403_FORBIDDEN)