"""Celery entrypoint.

Worker:  celery -A celery_worker.celery_app worker -l info
Beat:    celery -A celery_worker.celery_app beat -l info
"""
from app.celery_app import celery_app
from app import tasks  # noqa: F401  (register tasks)

__all__ = ["celery_app"]
