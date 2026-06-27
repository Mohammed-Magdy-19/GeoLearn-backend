"""
config/celery.py

Celery application bootstrap.
Tasks are auto-discovered from every installed app's tasks.py file.
"""

import os
from celery import Celery

# Point Celery at Django's settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("teaching_platform")

# Read all CELERY_* keys from Django settings — no separate celery config needed
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every app listed in INSTALLED_APPS
app.autodiscover_tasks()