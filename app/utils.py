"""Shared helpers: logging, hashing, dedup cache, language detection."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

import redis

from app.config import settings

_LOG_CONFIGURED = False


def configure_logging() -> None:
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    _LOG_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


# --------------------------------------------------------------------------- #
# Hashing / dedup
# --------------------------------------------------------------------------- #
def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def make_news_id(source: str, url: str | None, title: str) -> str:
    """Deterministic id so duplicates collide on the primary key."""
    basis = url.strip() if url else normalize_text(title)
    digest = hashlib.sha256(f"{source}::{basis}".encode()).hexdigest()
    return digest


_redis_client: "redis.Redis | None" = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


_SEEN_KEY = "aibot:seen_news"


def already_seen(news_id: str) -> bool:
    """Fast pre-check against a Redis set (best-effort; DB PK is the real guard)."""
    try:
        return bool(get_redis().sismember(_SEEN_KEY, news_id))
    except redis.RedisError:  # pragma: no cover - cache is optional
        return False


def mark_seen(news_id: str) -> None:
    try:
        get_redis().sadd(_SEEN_KEY, news_id)
    except redis.RedisError:  # pragma: no cover
        pass


# --------------------------------------------------------------------------- #
# Language detection
# --------------------------------------------------------------------------- #
def detect_language(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect(text)
    except Exception:
        # crude fallback: cyrillic => ru, otherwise en
        return "ru" if re.search(r"[а-яёА-ЯЁ]", text) else "en"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
