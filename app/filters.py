"""Relevance filtering: keywords, language, source, duplicates."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Keyword, NewsItem
from app.news_parser.base import ParsedNews
from app.utils import already_seen, detect_language, get_logger, normalize_text

logger = get_logger(__name__)


@dataclass
class FilterDecision:
    passed: bool
    reason: str = "ok"


def load_keywords(db: Session) -> list[str]:
    words = db.execute(select(Keyword.word)).scalars().all()
    return [normalize_text(w) for w in words if w and w.strip()]


def matches_keywords(text: str, keywords: list[str], mode: str = "any") -> bool:
    if not keywords:
        return True  # no keywords configured => accept everything
    haystack = normalize_text(text)
    hits = [kw for kw in keywords if kw in haystack]
    return len(hits) == len(keywords) if mode == "all" else bool(hits)


def language_allowed(text: str, allowed: list[str] | None) -> bool:
    if not allowed:
        return True
    lang = detect_language(text)
    return lang is None or lang in allowed


def is_duplicate(db: Session, news_id: str) -> bool:
    if already_seen(news_id):
        return True
    return db.get(NewsItem, news_id) is not None


def evaluate(
    item: ParsedNews,
    db: Session,
    *,
    keywords: list[str] | None = None,
) -> FilterDecision:
    """Run the full filter chain for a freshly parsed item."""
    if is_duplicate(db, item.news_id):
        return FilterDecision(False, "duplicate")

    text = " ".join(filter(None, [item.title, item.summary, item.raw_text]))

    if not language_allowed(text, settings.filter_languages):
        return FilterDecision(False, "language_not_allowed")

    kws = load_keywords(db) if keywords is None else keywords
    if not matches_keywords(text, kws, settings.keyword_match_mode):
        return FilterDecision(False, "no_keyword_match")

    return FilterDecision(True, "ok")
