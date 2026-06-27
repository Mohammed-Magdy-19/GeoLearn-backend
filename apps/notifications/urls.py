# apps/notifications/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", views.UnreadCountView.as_view(), name="notification-unread-count"),
    path("<str:notification_id>/read/", views.MarkReadView.as_view(), name="notification-mark-read"),
    path("read-all/", views.MarkAllReadView.as_view(), name="notification-mark-all-read"),
]
