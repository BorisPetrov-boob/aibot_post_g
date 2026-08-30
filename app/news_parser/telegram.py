"""Public Telegram channel parser via Telethon."""
from __future__ import annotations

import asyncio

from app.config import settings
from app.news_parser.base import ParsedNews
from app.utils import get_logger

logger = get_logger(__name__)


async def _fetch(username: str, limit: int) -> list[ParsedNews]:
    try:
        from telethon import TelegramClient
    except ImportError as exc:  # pragma: no cover
        logger.error("telethon is not installed: %s", exc)
        return []

    if not (settings.telegram_api_id and settings.telegram_api_hash):
        logger.warning("Telegram API credentials are not configured — skipping %s", username)
        return []

    client = TelegramClient(
        settings.telegram_session, settings.telegram_api_id, settings.telegram_api_hash
    )
    items: list[ParsedNews] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            logger.error(
                "Telethon session '%s' is not authorized. Run scripts/telethon_login.py once.",
                settings.telegram_session,
            )
            return []

        entity = await client.get_entity(username)
        channel_name = getattr(entity, "title", username)
        async for message in client.iter_messages(entity, limit=limit):
            text = (message.message or "").strip()
            if not text:
                continue
            first_line = text.splitlines()[0][:200]
            link = None
            uname = getattr(entity, "username", None)
            if uname:
                link = f"https://t.me/{uname}/{message.id}"
            items.append(
                ParsedNews(
                    title=first_line,
                    source=f"tg:{username}",
                    summary=text[:500],
                    url=link,
                    raw_text=text,
                    published_at=message.date,
                )
            )
    finally:
        await client.disconnect()

    logger.info("Fetched %d messages from %s", len(items), channel_name)
    return items


def parse_telegram_channel(username: str, *, limit: int = 20) -> list[ParsedNews]:
    """Sync entrypoint used by Celery tasks."""
    try:
        return asyncio.run(_fetch(username, limit))
    except RuntimeError:
        # already inside an event loop (rare in Celery) -> use a fresh loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_fetch(username, limit))
        finally:
            loop.close()
