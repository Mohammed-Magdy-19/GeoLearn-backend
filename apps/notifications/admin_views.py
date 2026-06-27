"""
apps/notifications/admin_views.py

Admin notification management endpoints.

Endpoints:
    GET    /api/admin/notifications/       — List all notifications
    POST   /api/admin/notifications/       — Create manual notification (broadcast)
    DELETE /api/admin/notifications/<id>/   — Delete a notification
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.pagination import PageNumberPagination

from .models import Notification
from .serializers import AdminNotificationSerializer, AdminNotificationCreateSerializer
from .services import create_admin_notification


class AdminNotificationPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminNotificationListCreateView(APIView):
    """
    GET  /api/admin/notifications/ — List all notifications (paginated)
    POST /api/admin/notifications/ — Create a new admin notification
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = Notification.objects.all().order_by("-created_at")

        # Optional type filter
        notif_type = request.query_params.get("type", "").strip()
        if notif_type:
            queryset = queryset.filter(type=notif_type)

        # Search
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(message__icontains=search)
            )

        paginator = AdminNotificationPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AdminNotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = AdminNotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = create_admin_notification(
            title=serializer.validated_data["title"],
            message=serializer.validated_data["message"],
            link=serializer.validated_data.get("link", ""),
            created_by=request.user,
        )

        return Response(
            AdminNotificationSerializer(notification).data,
            status=status.HTTP_201_CREATED,
        )


class AdminNotificationDeleteView(APIView):
    """
    DELETE /api/admin/notifications/<id>/ — Delete a notification
    """

    permission_classes = [IsAdminUser]

    def delete(self, request, notification_id: str):
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminNotificationDeleteAllView(APIView):
    """
    POST /api/admin/notifications/delete-all/ — Delete all notifications
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        count, _ = Notification.objects.all().delete()
        return Response(
            {"detail": f"تم حذف {count} إشعار بنجاح."},
            status=status.HTTP_200_OK,
        )

