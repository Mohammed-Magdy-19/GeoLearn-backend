"""
apps/notifications/models.py

Notification system models.

Two models:
  - Notification: The notification content (system or admin-defined)
  - UserNotification: Per-user read state tracking
"""

import uuid
from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    A notification message that can be broadcast to all users.

    Types:
      - "system": Auto-generated when admin performs CRUD operations
      - "admin": Manually created by admin via the dashboard
    """

    TYPE_CHOICES = [
        ("system", "نظام"),
        ("admin", "إدارية"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default="system",
        db_index=True,
        help_text="Notification origin: system-generated or admin-created",
    )
    title = models.CharField(
        max_length=255,
        help_text="Short notification title",
    )
    message = models.TextField(
        help_text="Full notification message body",
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional deep-link URL (e.g. /courses/geo101)",
    )
    is_global = models.BooleanField(
        default=True,
        help_text="If True, broadcast to all active users",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
        help_text="Admin user who created this notification (null for system)",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self) -> str:
        return f"[{self.get_type_display()}] {self.title}"


class UserNotification(models.Model):
    """
    Per-user read state for each notification.

    Created when a notification is broadcast. Tracks whether
    the user has read the notification and when.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="user_entries",
        db_index=True,
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the user has read this notification",
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the user read the notification",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_notifications"
        ordering = ["-notification__created_at"]
        verbose_name = "User Notification"
        verbose_name_plural = "User Notifications"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notification"],
                name="unique_user_notification",
            ),
        ]

    def __str__(self) -> str:
        status = "✓" if self.is_read else "○"
        return f"{status} {self.user} — {self.notification.title}"
