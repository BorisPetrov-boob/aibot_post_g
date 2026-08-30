"""Helper for persisting error-log entries."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ErrorLog
from app.utils import get_logger

logger = get_logger(__name__)


def record_error(db: Session, scope: str, message: str, context: str | None = None) -> None:
    logger.error("[%s] %s | %s", scope, message, context or "")
    try:
        db.add(ErrorLog(scope=scope[:64], message=str(message), context=context))
        db.flush()
    except Exception:  # noqa: BLE001 - logging must never raise
        db.rollback()
        logger.exception("Failed to persist ErrorLog")
