# apps/notifications/admin_urls.py
from django.urls import path
from . import admin_views

urlpatterns = [
    path("", admin_views.AdminNotificationListCreateView.as_view(), name="admin-notification-list-create"),
    path("delete-all/", admin_views.AdminNotificationDeleteAllView.as_view(), name="admin-notification-delete-all"),
    path("<str:notification_id>/", admin_views.AdminNotificationDeleteView.as_view(), name="admin-notification-delete"),
]

