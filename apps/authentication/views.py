"""
apps/authentication/views.py

Authentication API endpoints:
  POST /api/auth/register/        → Create new account
  POST /api/auth/login/           → Get access + refresh token pair
  POST /api/auth/token/refresh/   → Rotate refresh token, get new access token
  GET  /api/auth/me/              → Get authenticated user's profile
"""

from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    UserRegistrationSerializer,
    UserProfileSerializer,
    CustomTokenObtainPairSerializer,
)


class RegisterView(CreateAPIView):
    """
    POST /api/auth/register/

    Public endpoint — no authentication required.
    Creates a new user account and returns the user profile.

    Does NOT return tokens on registration. The client follows up
    with a login request to obtain tokens. This is a deliberate
    separation of concerns: registration ≠ authentication.

    Request body:
        {
            "username":         "ahmed_dev",
            "full_name":        "Ahmed Hassan",
            "email":            "ahmed@example.com",   ← optional
            "password":         "securePass123",
            "password_confirm": "securePass123"
        }

    Response 201:
        {
            "id":        1,
            "username":  "ahmed_dev",
            "full_name": "Ahmed Hassan",
            "email":     "ahmed@example.com"
        }
    """

    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]  # No JWT required to register

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Return the created profile with 201 Created
        profile = UserProfileSerializer(user)
        return Response(profile.data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login/

    Public endpoint. Extends SimpleJWT's TokenObtainPairView to use our
    CustomTokenObtainPairSerializer which:
      - Uses `username` as the credential field
      - Embeds user metadata in the token payload
      - Returns user profile data alongside the token pair

    Request body:
        {
            "username": "ahmed_dev",
            "password": "securePass123"
        }

    Response 200:
        {
            "access":  "<access_jwt>",
            "refresh": "<refresh_jwt>",
            "user": { "id": 1, "username": "ahmed_dev", "full_name": "Ahmed Hassan", ... }
        }
    """

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]


class CustomTokenRefreshView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/

    Public endpoint (the refresh token IS the credential here).
    SimpleJWT handles rotation automatically based on SIMPLE_JWT settings:
      - Issues a new access token
      - Issues a new refresh token  (ROTATE_REFRESH_TOKENS = True)
      - Blacklists the old refresh token (BLACKLIST_AFTER_ROTATION = True)

    Request body:
        { "refresh": "<refresh_jwt>" }

    Response 200:
        { "access": "<new_access_jwt>", "refresh": "<new_refresh_jwt>" }
    """

    permission_classes = [AllowAny]


class CurrentUserView(RetrieveUpdateAPIView):
    """
    GET /api/auth/me/
    PATCH /api/auth/me/

    Protected endpoint — requires valid Bearer token in the Authorization header.
    Returns the full profile of the currently authenticated user.
    Useful for hydrating the Zustand store on page reload.

    Response 200:
        {
            "id":          1,
            "username":    "ahmed_dev",
            "full_name":   "Ahmed Hassan",
            "email":       "ahmed@example.com",
            "avatar":      null,
            "date_joined": "2024-01-15T10:30:00Z"
        }
    """

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # request.user is automatically populated by JWTAuthentication middleware
        return self.request.user
