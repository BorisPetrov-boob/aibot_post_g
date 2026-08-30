"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import PostStatus, SourceType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------- Source --------------------------- #
class SourceCreate(BaseModel):
    type: SourceType
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1024, description="Site URL or @username for TG")
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    enabled: bool | None = None


class SourceOut(ORMModel):
    id: str
    type: SourceType
    name: str
    url: str
    enabled: bool
    created_at: datetime


# --------------------------- Keyword --------------------------- #
class KeywordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=255)


class KeywordOut(ORMModel):
    id: str
    word: str
    created_at: datetime


# --------------------------- NewsItem --------------------------- #
class NewsItemOut(ORMModel):
    id: str
    title: str
    url: str | None
    summary: str
    source: str
    published_at: datetime
    raw_text: str | None
    language: str | None
    created_at: datetime


# --------------------------- Post --------------------------- #
class PostOut(ORMModel):
    id: str
    news_id: str | None
    generated_text: str
    status: PostStatus
    error: str | None
    tg_message_id: int | None
    created_at: datetime
    published_at: datetime | None


# --------------------------- Generation --------------------------- #
class GenerateRequest(BaseModel):
    news_id: str | None = Field(default=None, description="Generate from a stored NewsItem")
    title: str | None = None
    summary: str | None = None
    raw_text: str | None = None
    url: str | None = None
    source: str | None = None
    model: str | None = Field(default=None, description="Override OpenAI model")
    persist: bool = Field(default=False, description="Save the result as a Post")
    publish: bool = Field(default=False, description="Also enqueue publication (needs persist)")


class GenerateResponse(BaseModel):
    generated_text: str
    post_id: str | None = None
    used_offline_stub: bool = False


# --------------------------- ErrorLog --------------------------- #
class ErrorLogOut(ORMModel):
    id: str
    scope: str
    message: str
    context: str | None
    created_at: datetime


class SimpleMessage(BaseModel):
    detail: str
