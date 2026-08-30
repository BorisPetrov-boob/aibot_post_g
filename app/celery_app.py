"""Celery application + Beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (handy for custom schedules)

from app.config import settings

celery_app = Celery(
    "aibot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_track_started=True,
    worker_max_tasks_per_child=200,
    task_default_retry_delay=30,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "collect-news-every-30-min": {
        "task": "app.tasks.collect_all_sources",
        "schedule": float(settings.parse_interval_minutes * 60),
    },
}
