"""
apps/authentication/serializers.py

Serializers handle JSON ↔ Python conversion and validation for auth endpoints.

Serializers in this file:
  - UserRegistrationSerializer       → POST /api/auth/register/
  - UserProfileSerializer            → GET  /api/auth/me/
  - CustomTokenObtainPairSerializer  → POST /api/auth/login/ (extends SimpleJWT)
"""

import re
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

# Username must be 3–50 chars: letters, digits, underscores, hyphens only
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Validates and creates a new CustomUser.

    Adds:
      - password_confirm field for double-entry validation
      - write_only on both password fields (never returned in responses)
      - username format validation via regex
      - username uniqueness is enforced by the model's unique=True constraint
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        help_text="Minimum 8 characters.",
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Must match the password field exactly.",
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate_username(self, value: str) -> str:
        """
        Reject usernames that contain spaces or special characters.
        Normalize to lowercase so 'Ahmed' and 'ahmed' are the same account.
        """
        cleaned = value.strip().lower()
        if not _USERNAME_RE.match(cleaned):
            raise serializers.ValidationError(
                "Username must be 3–50 characters and contain only "
                "letters, digits, underscores (_), or hyphens (-)."
            )
        return cleaned

    def validate(self, attrs: dict) -> dict:
        """Cross-field validation: ensure both password entries match."""
        if attrs.get("password") != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data: dict) -> User:
        """
        Delegate user creation to CustomUserManager.create_user()
        which handles proper password hashing via set_password().
        """
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            email=validated_data.get("email"),
        )


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the authenticated user's profile.
    Returned from GET and PATCH /api/auth/me/ — never exposes password-related fields.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "phone_number",
            "bio",
            "avatar",
            "is_staff",
            "is_superuser",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "username",
            "is_staff",
            "is_superuser",
            "date_joined",
        ]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends SimpleJWT's default login serializer to:
      1. Embed user metadata inside the access token payload
      2. Return user profile data alongside the token pair in the login response

    This saves the frontend an extra /me/ API call right after login.
    """

    @classmethod
    def get_token(cls, user: User):
        """
        Add custom claims to the JWT payload.
        These are readable client-side (JWT is base64, not encrypted).
        Never put sensitive data here.
        """
        token = super().get_token(user)

        # Embed non-sensitive identity data for quick client-side access
        token["username"] = user.username
        token["full_name"] = user.full_name
        token["is_staff"] = user.is_staff

        return token

    def validate(self, attrs: dict) -> dict:
        """
        After standard validation, append the user profile to the response body.
        The frontend stores this in Zustand without needing a follow-up /me/ call.
        """
        data = super().validate(attrs)

        # Append profile data alongside the token pair
        data["user"] = UserProfileSerializer(self.user).data

        return data