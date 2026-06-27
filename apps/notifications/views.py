"""
apps/notifications/views.py

User-facing notification endpoints.

Endpoints:
    GET    /api/notifications/              — List user's notifications (paginated)
    GET    /api/notifications/unread-count/  — Get unread count
    POST   /api/notifications/<id>/read/     — Mark single as read
    POST   /api/notifications/read-all/      — Mark all as read
"""

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import Notification, UserNotification
from .serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 50


class NotificationListView(generics.ListAPIView):
    """
    GET /api/notifications/

    Returns the authenticated user's notifications, newest first.
    Each notification includes is_read and read_at from UserNotification.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        # Get notification IDs for this user
        user_notifs = UserNotification.objects.filter(
            user=self.request.user
        ).select_related("notification")

        # Annotate each notification with its read state
        notification_ids = user_notifs.values_list("notification_id", flat=True)
        notifications = Notification.objects.filter(id__in=notification_ids)

        return notifications

    def list(self, request, *args, **kwargs):
        # Custom list to include is_read from UserNotification
        user_notifs = (
            UserNotification.objects.filter(user=request.user)
            .select_related("notification")
            .order_by("-notification__created_at")
        )

        # Paginate
        page = self.paginate_queryset(user_notifs)
        if page is not None:
            data = []
            for un in page:
                notif = un.notification
                notif.is_read = un.is_read
                notif.read_at = un.read_at
                data.append(NotificationSerializer(notif).data)
            return self.get_paginated_response(data)

        data = []
        for un in user_notifs:
            notif = un.notification
            notif.is_read = un.is_read
            notif.read_at = un.read_at
            data.append(NotificationSerializer(notif).data)
        return Response(data)


class UnreadCountView(APIView):
    """
    GET /api/notifications/unread-count/

    Returns the number of unread notifications for the user.
    Response: { "count": 5 }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = UserNotification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return Response({"count": count})


class MarkReadView(APIView):
    """
    POST /api/notifications/<id>/read/

    Mark a single notification as read.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id: str):
        try:
            user_notif = UserNotification.objects.get(
                user=request.user,
                notification_id=notification_id,
            )
        except UserNotification.DoesNotExist:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user_notif.is_read:
            user_notif.is_read = True
            user_notif.read_at = timezone.now()
            user_notif.save(update_fields=["is_read", "read_at"])

        return Response({"detail": "Marked as read."})


class MarkAllReadView(APIView):
    """
    POST /api/notifications/read-all/

    Mark all unread notifications as read for the user.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = UserNotification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        return Response({
            "detail": f"Marked {updated} notification(s) as read.",
            "count": updated,
        })
