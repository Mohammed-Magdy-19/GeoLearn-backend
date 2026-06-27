"""
apps/notifications/services.py

Utility functions for creating and broadcasting notifications.
Used by admin viewsets to auto-generate system notifications.
"""

from django.contrib.auth import get_user_model
from .models import Notification, UserNotification

User = get_user_model()


def create_system_notification(
    title: str,
    message: str,
    link: str = "",
) -> Notification:
    """
    Create a system notification and broadcast it to all active users.

    Args:
        title: Short notification title (e.g. "🎓 كورس جديد")
        message: Full message body
        link: Optional deep-link URL

    Returns:
        The created Notification instance
    """
    notification = Notification.objects.create(
        type="system",
        title=title,
        message=message,
        link=link,
        is_global=True,
        created_by=None,
    )

    _broadcast_to_all_users(notification)
    return notification


def create_admin_notification(
    title: str,
    message: str,
    link: str = "",
    created_by=None,
) -> Notification:
    """
    Create an admin-defined notification and broadcast to all active users.

    Args:
        title: Short notification title
        message: Full message body
        link: Optional deep-link URL
        created_by: The admin user creating this notification

    Returns:
        The created Notification instance
    """
    notification = Notification.objects.create(
        type="admin",
        title=title,
        message=message,
        link=link,
        is_global=True,
        created_by=created_by,
    )

    _broadcast_to_all_users(notification)
    return notification


def _broadcast_to_all_users(notification: Notification) -> int:
    """
    Create UserNotification entries for all active users.

    Returns the number of entries created.
    """
    active_users = User.objects.filter(is_active=True)
    entries = [
        UserNotification(user=user, notification=notification)
        for user in active_users
    ]
    UserNotification.objects.bulk_create(entries, ignore_conflicts=True)
    return len(entries)
