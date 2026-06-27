"""
apps/authentication/apps.py

AppConfig for the authentication domain.
The `name` must match the dotted path in INSTALLED_APPS.
"""

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "Authentication"