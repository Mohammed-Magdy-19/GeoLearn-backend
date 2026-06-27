"""
apps/authentication/models.py

CustomUser model — the single source of truth for all user identity.

Design decisions:
  - `username` is the login identifier (unique, indexed, lowercased on save)
  - AbstractBaseUser gives us full control over fields and auth mechanics
  - PermissionsMixin adds is_superuser, groups, and user_permissions (needed for Django admin)
  - db_index=True on username ensures fast O(log n) lookups on every JWT-authenticated request
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone

from .managers import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Platform user identified by username instead of the built-in email/username combo.

    Fields:
        username      — unique login identifier (indexed, lowercased, max 50 chars)
        full_name     — display name shown in UI and watermarks
        email         — optional; used for receipts and notifications
        is_active     — soft-delete flag; False = account suspended
        is_staff      — True = can access Django admin
        date_joined   — immutable registration timestamp
        avatar        — optional profile picture stored in MEDIA_ROOT/avatars/
    """

    username = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,  # Critical: JWT validation queries this field on every request
        verbose_name="Username",
        help_text="3–50 characters. Letters, digits, underscores, and hyphens only.",
    )
    full_name = models.CharField(
        max_length=150,
        verbose_name="Full Name",
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email Address",
        help_text="Optional — used for receipts and notifications.",
    )
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Profile Picture",
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Phone Number",
    )
    bio = models.TextField(
        blank=True,
        null=True,
        verbose_name="Biography",
    )

    # ── Django's required admin/permissions fields ─────────────
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to suspend the account without deleting it.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Grants access to the Django admin interface.",
    )
    date_joined = models.DateTimeField(default=timezone.now, editable=False)

    # ── Manager ───────────────────────────────────────────────
    objects = CustomUserManager()

    # ── Auth field ────────────────────────────────────────────
    # Tell Django to use `username` as the login credential field
    USERNAME_FIELD = "username"

    # Fields prompted when running `createsuperuser` (username is always prompted)
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return f"{self.full_name} (@{self.username})"

    @property
    def short_name(self) -> str:
        """Returns the first word of the full name for greeting labels."""
        return self.full_name.split()[0] if self.full_name else self.username

    def save(self, *args, **kwargs):
        """Enforce lowercase on username before every save."""
        self.username = self.username.strip().lower()
        super().save(*args, **kwargs)
