"""Thin wrapper around the OpenAI Chat Completions API with error handling."""
from __future__ import annotations

from app.config import settings
from app.utils import get_logger

logger = get_logger(__name__)


class AIError(RuntimeError):
    """Raised for any AI-provider failure the caller should handle/retry."""


class AIRateLimitError(AIError):
    pass


class AIUnavailableError(AIError):
    pass


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings.openai_api_key:
        raise AIUnavailableError("OPENAI_API_KEY is not configured")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIUnavailableError("openai package is not installed") from exc

    _client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        max_retries=settings.openai_max_retries,
        timeout=settings.openai_timeout,
    )
    return _client


def generate_chat(system_prompt: str, user_content: str, *, model: str | None = None) -> str:
    """Call the model and return plain text. Translates SDK errors into AIError."""
    client = _get_client()
    model = model or settings.openai_model

    try:
        from openai import APIError, APIConnectionError, RateLimitError
    except ImportError:  # pragma: no cover
        APIError = APIConnectionError = RateLimitError = Exception  # type: ignore

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
            max_tokens=500,
        )
    except RateLimitError as exc:  # type: ignore[misc]
        logger.warning("OpenAI rate limit: %s", exc)
        raise AIRateLimitError(str(exc)) from exc
    except (APIConnectionError,) as exc:  # type: ignore[misc]
        logger.error("OpenAI connection error: %s", exc)
        raise AIUnavailableError(str(exc)) from exc
    except APIError as exc:  # type: ignore[misc]
        logger.error("OpenAI API error: %s", exc)
        raise AIUnavailableError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected OpenAI failure")
        raise AIError(str(exc)) from exc

    choice = resp.choices[0].message.content if resp.choices else None
    if not choice:
        raise AIError("Empty response from AI provider")
    return choice.strip()
