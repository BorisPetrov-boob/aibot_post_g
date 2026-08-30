"""Build the prompt and turn raw news material into a Telegram-ready post."""
from __future__ import annotations

from dataclasses import dataclass

from app.ai.openai_client import AIError, AIUnavailableError, generate_chat
from app.config import settings
from app.utils import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationInput:
    title: str | None = None
    summary: str | None = None
    raw_text: str | None = None
    url: str | None = None
    source: str | None = None

    def as_user_content(self) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"Заголовок: {self.title}")
        body = self.raw_text or self.summary
        if body:
            parts.append(f"Текст новости: {body}")
        if self.source:
            parts.append(f"Источник: {self.source}")
        if self.url:
            parts.append(f"Ссылка: {self.url}")
        return "\n".join(parts).strip()


def _offline_stub(data: GenerationInput) -> str:
    """Deterministic fallback when no AI key is configured (keeps the pipeline usable)."""
    headline = data.title or (data.summary or "Новость")[:80]
    body = (data.summary or data.raw_text or "").strip()
    body = (body[:280] + "…") if len(body) > 280 else body
    tail = f"\n\n🔗 Подробнее: {data.url}" if data.url else ""
    return (
        f"📰 {headline}\n\n{body}{tail}\n\n"
        "👉 Подписывайтесь на канал, чтобы не пропустить свежие новости!"
    )


def generate_post(data: GenerationInput, *, model: str | None = None) -> str:
    content = data.as_user_content()
    if not content:
        raise ValueError("Nothing to generate from: title/summary/raw_text are all empty")

    if not settings.openai_enabled:
        logger.warning("OpenAI disabled — returning offline stub post")
        return _offline_stub(data)

    try:
        return generate_chat(settings.ai_system_prompt, content, model=model)
    except AIUnavailableError:
        logger.error("AI unavailable — falling back to offline stub")
        return _offline_stub(data)
    except AIError:
        raise
