"""Publish generated posts to the target Telegram channel via Telethon."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import settings
from app.telegram.bot import build_client
from app.utils import get_logger

logger = get_logger(__name__)


class PublishError(RuntimeError):
    pass


@dataclass
class PublishResult:
    ok: bool
    message_id: int | None = None
    error: str | None = None
    skipped: bool = False


async def _send(text: str) -> PublishResult:
    if not settings.telethon_enabled:
        logger.warning("Telethon not configured — publish skipped")
        return PublishResult(ok=False, skipped=True, error="telethon_not_configured")

    client = build_client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return PublishResult(
                ok=False, error="telethon_session_not_authorized"
            )
        entity = await client.get_entity(settings.telegram_target_channel)
        msg = await client.send_message(entity, text, link_preview=True)
        logger.info("Published message %s to %s", msg.id, settings.telegram_target_channel)
        return PublishResult(ok=True, message_id=msg.id)
    finally:
        await client.disconnect()


def publish_text(text: str) -> PublishResult:
    """Sync entrypoint for Celery tasks."""
    if not text or not text.strip():
        raise PublishError("Refusing to publish empty text")
    try:
        return asyncio.run(_send(text))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_send(text))
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Publish failed")
        return PublishResult(ok=False, error=str(exc))
