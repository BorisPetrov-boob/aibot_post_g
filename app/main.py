"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.endpoints import ALL_ROUTERS
from app.config import settings
from app.database import init_db
from app.utils import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    logger.info("%s started (debug=%s)", settings.app_name, settings.debug)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "AI-генератор постов для Telegram: парсинг новостей (сайты + Telegram), "
        "фильтрация, генерация постов через OpenAI, публикация через Telethon."
    ),
    lifespan=lifespan,
)

for _router in ALL_ROUTERS:
    app.include_router(_router, prefix=settings.api_prefix)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "openai_enabled": settings.openai_enabled,
        "telethon_enabled": settings.telethon_enabled,
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
