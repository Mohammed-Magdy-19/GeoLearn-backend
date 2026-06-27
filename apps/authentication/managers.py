"""
apps/authentication/managers.py

Custom manager for CustomUser.

Why a custom manager?
Django's default UserManager ships with a `username` field already,
but its create_user() signature assumes extra fields we don't need.
We override it here to keep the interface clean and explicit,
and to enforce our own normalization logic on the username.
"""

from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    """
    Manager where `username` is the unique identifier for authentication.
    Replaces Django's default manager to keep the interface explicit
    and enforce normalization before saving.
    """

    def create_user(self, username: str, password: str = None, **extra_fields):
        """
        Create and save a regular user with the given username and password.

        Args:
            username:     Unique login handle chosen by the user (e.g. "ahmed_dev")
            password:     Plain-text password — will be hashed before storage
            **extra_fields: Any additional model fields (full_name, email, etc.)

        Returns:
            CustomUser instance

        Raises:
            ValueError: If username is not provided
        """
        if not username:
            raise ValueError("The username field is required.")

        # Normalize: lowercase and strip whitespace for consistent lookups
        username = self._normalize_username(username)

        user = self.model(username=username, **extra_fields)
        user.set_password(password)  # Hashes with PBKDF2 by default
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str, **extra_fields):
        """
        Create and save a superuser (Django admin access).
        Enforces is_staff=True and is_superuser=True.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)

    @staticmethod
    def _normalize_username(username: str) -> str:
        """
        Lowercase and strip whitespace so 'Ahmed' and 'ahmed' resolve
        to the same account — prevents accidental duplicate registrations.
        """
        return username.strip().lower()
