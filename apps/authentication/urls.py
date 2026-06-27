"""
apps/authentication/urls.py

URL patterns for the authentication app.
All routes are prefixed with /api/auth/ from config/urls.py.
"""

from django.urls import path
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CurrentUserView,
)

urlpatterns = [
    # ── Account Creation ───────────────────────────────────────
    path("register/", RegisterView.as_view(), name="auth-register"),

    # ── Token Acquisition ──────────────────────────────────────
    path("login/", CustomTokenObtainPairView.as_view(), name="auth-login"),

    # ── Token Rotation ─────────────────────────────────────────
    # Frontend Axios interceptor calls this automatically on 401 errors
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="auth-token-refresh"),

    # ── Authenticated Profile ──────────────────────────────────
    path("me/", CurrentUserView.as_view(), name="auth-me"),
]