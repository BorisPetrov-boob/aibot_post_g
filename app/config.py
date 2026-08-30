"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AI_PROMPT = (
    "Сделай краткое, интересное описание новости для Telegram-канала. "
    "Пиши живо и лаконично (2-4 предложения), добавь подходящие emoji "
    "и заверши коротким call to action. Не выдумывай фактов, опирайся только "
    "на предоставленный текст. Отвечай на языке исходной новости."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core / API ---
    app_name: str = "AI Telegram Post Generator"
    debug: bool = False
    api_prefix: str = "/api"

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg2://aibot:aibot@localhost:5432/aibot"
    )

    # --- Celery / broker ---
    celery_broker_url: str = Field(default="amqp://guest:guest@localhost:5672//")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")

    # --- Redis (dedup / filter cache) ---
    redis_url: str = Field(default="redis://localhost:6379/1")

    # --- Scheduling ---
    parse_interval_minutes: int = 30

    # --- OpenAI ---
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    openai_max_retries: int = 3
    openai_timeout: float = 60.0
    ai_system_prompt: str = DEFAULT_AI_PROMPT

    # --- Telegram / Telethon ---
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str = "aibot"
    telegram_target_channel: str | None = None  # @channel or -100... id

    # --- Filtering ---
    filter_languages: list[str] = Field(default_factory=lambda: ["ru", "en"])
    keyword_match_mode: str = "any"  # "any" | "all"; empty keyword list => pass all

    @field_validator(
        "openai_api_key",
        "openai_base_url",
        "telegram_api_id",
        "telegram_api_hash",
        "telegram_target_channel",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def telethon_enabled(self) -> bool:
        return bool(
            self.telegram_api_id
            and self.telegram_api_hash
            and self.telegram_target_channel
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
