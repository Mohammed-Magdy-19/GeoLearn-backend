"""
apps/notifications/serializers.py

DRF serializers for the notification system.
"""

from rest_framework import serializers
from .models import Notification, UserNotification


class NotificationSerializer(serializers.ModelSerializer):
    """
    User-facing notification serializer.
    Includes the read state from the UserNotification join.
    """

    is_read = serializers.BooleanField(read_only=True)
    read_at = serializers.DateTimeField(read_only=True)
    type_display = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "type_display",
            "title",
            "message",
            "link",
            "created_at",
            "is_read",
            "read_at",
        ]

    def get_type_display(self, obj: Notification) -> str:
        return obj.get_type_display()


class AdminNotificationSerializer(serializers.ModelSerializer):
    """
    Admin-facing serializer for listing and creating notifications.
    """

    type_display = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    recipient_count = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "type_display",
            "title",
            "message",
            "link",
            "is_global",
            "created_by",
            "created_by_name",
            "recipient_count",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "type",
            "type_display",
            "created_by",
            "created_by_name",
            "recipient_count",
            "created_at",
        ]

    def get_type_display(self, obj: Notification) -> str:
        return obj.get_type_display()

    def get_created_by_name(self, obj: Notification) -> str:
        if obj.created_by:
            return obj.created_by.full_name or obj.created_by.username or obj.created_by.email
        return "النظام"

    def get_recipient_count(self, obj: Notification) -> int:
        return obj.user_entries.count()


class AdminNotificationCreateSerializer(serializers.Serializer):
    """
    Write-only serializer for creating admin notifications.
    """

    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    link = serializers.CharField(max_length=500, required=False, default="")
