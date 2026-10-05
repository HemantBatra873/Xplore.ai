from celery import Celery

from app.core.config import settings

# Celery application
# app name; broker and result backend use the same Redis
celery_app = Celery("worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

# Celery settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Optional result expiry (e.g. one day)
    result_expires=86400,
)

# Task modules to import (autodiscover)
celery_app.autodiscover_tasks(["app.worker.tasks"])
