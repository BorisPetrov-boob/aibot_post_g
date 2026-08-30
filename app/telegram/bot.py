"""Telethon client factory / auth helpers."""
from __future__ import annotations

from app.config import settings
from app.utils import get_logger

logger = get_logger(__name__)


def build_client():
    """Create (not connect) a TelegramClient from configured credentials."""
    from telethon import TelegramClient

    if not (settings.telegram_api_id and settings.telegram_api_hash):
        raise RuntimeError("TELEGRAM_API_ID / TELEGRAM_API_HASH are not configured")

    return TelegramClient(
        settings.telegram_session,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )


async def interactive_login() -> None:
    """One-time console login to create a reusable .session file."""
    client = build_client()
    await client.start()  # prompts for phone + code on first run
    me = await client.get_me()
    logger.info("Authorized as %s (id=%s)", getattr(me, "username", me.id), me.id)
    await client.disconnect()
