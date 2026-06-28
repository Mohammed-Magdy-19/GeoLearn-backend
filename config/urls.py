"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
"""
config/urls.py

Root URL dispatcher.
Each domain app owns its own urls.py — we simply include them here.
All API routes are namespaced under /api/ to keep the URL space clean.
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    # ── Django Admin ──────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ── Authentication & JWT Token Endpoints ──────────────────
    # Handles: /api/auth/register/, /api/auth/login/,
    #          /api/auth/token/refresh/, /api/auth/me/
    path("api/auth/", include("apps.authentication.urls")),

    # ── Courses & Content ─────────────────────────────────────
    # Handles: /api/courses/, /api/courses/<id>/lessons/, etc.
    path("api/courses/", include("apps.courses.urls")),

    # ── Admin API Endpoints ───────────────────────────────────
    # Specific admin sub-routes MUST come before the generic api/admin/ include
    # Admin Notifications: /api/admin/notifications/
    path("api/admin/notifications/", include("apps.notifications.admin_urls")),
    # Generic admin (courses, modules, lessons, users, stats, summaries)
    path("api/admin/", include("apps.courses.admin_urls")),

    # ── Payments ──────────────────────────────────────────────
    # Handles: /api/payments/initiate/, /api/payments/paymob-webhook/
    path("api/payments/", include("apps.payments.urls")),

    # ── Notifications ────────────────────────────────────────
    # User: /api/notifications/, /api/notifications/unread-count/, etc.
    path("api/notifications/", include("apps.notifications.urls")),
]

# Serve media files in both development and production
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
