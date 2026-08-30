"""Common parser data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.utils import make_news_id, utcnow


@dataclass
class ParsedNews:
    title: str
    source: str
    summary: str = ""
    url: str | None = None
    raw_text: str | None = None
    published_at: datetime = field(default_factory=utcnow)

    @property
    def news_id(self) -> str:
        return make_news_id(self.source, self.url, self.title)

    def to_model_kwargs(self) -> dict:
        return {
            "id": self.news_id,
            "title": self.title[:1024],
            "url": self.url,
            "summary": self.summary or "",
            "source": self.source[:255],
            "published_at": self.published_at,
            "raw_text": self.raw_text,
        }
