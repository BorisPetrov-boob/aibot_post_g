"""Website news parser. Prefers RSS/Atom feeds, falls back to page metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from time import mktime

import requests

from app.news_parser.base import ParsedNews
from app.utils import get_logger

logger = get_logger(__name__)

USER_AGENT = "aibot-news-parser/1.0 (+https://example.com)"
TIMEOUT = 20


def _from_feed_entry(entry, source_name: str) -> ParsedNews | None:
    title = getattr(entry, "title", None)
    if not title:
        return None
    link = getattr(entry, "link", None)
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    published = utcnow_from_struct(getattr(entry, "published_parsed", None)) or (
        utcnow_from_struct(getattr(entry, "updated_parsed", None))
    )
    return ParsedNews(
        title=title.strip(),
        source=source_name,
        summary=_strip_html(summary),
        url=link,
        published_at=published or datetime.now(timezone.utc),
    )


def utcnow_from_struct(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        return datetime.fromtimestamp(mktime(struct_time), tz=timezone.utc)
    except (OverflowError, ValueError):
        return None


def _strip_html(value: str) -> str:
    if not value:
        return ""
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    except Exception:
        return value


def parse_site(url: str, source_name: str, *, limit: int = 20) -> list[ParsedNews]:
    """Fetch a site source and return parsed news items (newest first)."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch site %s: %s", url, exc)
        raise

    content_type = resp.headers.get("Content-Type", "")
    body = resp.content

    # --- Try RSS / Atom first ---
    try:
        import feedparser

        feed = feedparser.parse(body)
        if feed.entries:
            items = [_from_feed_entry(e, source_name) for e in feed.entries[:limit]]
            return [i for i in items if i]
    except Exception as exc:  # noqa: BLE001
        logger.debug("feedparser failed for %s: %s", url, exc)

    # --- Fallback: single item from page <title> + meta description ---
    if "html" in content_type or b"<html" in body[:2048].lower():
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(body, "html.parser")
            title = (soup.title.string if soup.title else None) or source_name
            desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            summary = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
            return [
                ParsedNews(
                    title=title.strip(),
                    source=source_name,
                    summary=summary,
                    url=url,
                    published_at=datetime.now(timezone.utc),
                )
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("HTML fallback failed for %s: %s", url, exc)

    logger.warning("No parseable content at %s", url)
    return []
