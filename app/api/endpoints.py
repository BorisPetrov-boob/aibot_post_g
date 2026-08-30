"""REST API: sources, keywords, news, posts, manual generation, logs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.generator import GenerationInput
from app.ai.generator import generate_post as ai_generate_post
from app.ai.openai_client import AIError
from app.api.schemas import (
    ErrorLogOut,
    GenerateRequest,
    GenerateResponse,
    KeywordCreate,
    KeywordOut,
    NewsItemOut,
    PostOut,
    SimpleMessage,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)
from app.config import settings
from app.database import get_db
from app.models import ErrorLog, Keyword, NewsItem, Post, PostStatus, Source

router = APIRouter()

# --------------------------------------------------------------------------- #
# Sources  /api/sources
# --------------------------------------------------------------------------- #
sources_router = APIRouter(prefix="/sources", tags=["sources"])


@sources_router.get("/", response_model=list[SourceOut])
def list_sources(
    enabled: bool | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Source).order_by(Source.created_at.desc())
    if enabled is not None:
        stmt = stmt.where(Source.enabled.is_(enabled))
    return db.execute(stmt).scalars().all()


@sources_router.post("/", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    source = Source(**payload.model_dump())
    db.add(source)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Source with this type+url already exists")
    db.refresh(source)
    return source


@sources_router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return source


@sources_router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: str, payload: SourceUpdate, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@sources_router.delete("/{source_id}", response_model=SimpleMessage)
def delete_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    db.delete(source)
    db.commit()
    return SimpleMessage(detail="deleted")


@sources_router.post("/{source_id}/parse", response_model=SimpleMessage)
def trigger_parse(source_id: str, db: Session = Depends(get_db)):
    if not db.get(Source, source_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    from app.tasks import parse_source

    parse_source.delay(source_id)
    return SimpleMessage(detail="parsing enqueued")


# --------------------------------------------------------------------------- #
# Keywords  /api/keywords
# --------------------------------------------------------------------------- #
keywords_router = APIRouter(prefix="/keywords", tags=["keywords"])


@keywords_router.get("/", response_model=list[KeywordOut])
def list_keywords(db: Session = Depends(get_db)):
    return db.execute(select(Keyword).order_by(Keyword.word)).scalars().all()


@keywords_router.post("/", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
def create_keyword(payload: KeywordCreate, db: Session = Depends(get_db)):
    kw = Keyword(word=payload.word.strip().lower())
    db.add(kw)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Keyword already exists")
    db.refresh(kw)
    return kw


@keywords_router.delete("/{keyword_id}", response_model=SimpleMessage)
def delete_keyword(keyword_id: str, db: Session = Depends(get_db)):
    kw = db.get(Keyword, keyword_id)
    if not kw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keyword not found")
    db.delete(kw)
    db.commit()
    return SimpleMessage(detail="deleted")


# --------------------------------------------------------------------------- #
# News  /api/news
# --------------------------------------------------------------------------- #
news_router = APIRouter(prefix="/news", tags=["news"])


@news_router.get("/", response_model=list[NewsItemOut])
def list_news(
    source: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(NewsItem).order_by(NewsItem.published_at.desc()).limit(limit).offset(offset)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    return db.execute(stmt).scalars().all()


@news_router.get("/{news_id}", response_model=NewsItemOut)
def get_news(news_id: str, db: Session = Depends(get_db)):
    item = db.get(NewsItem, news_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "News item not found")
    return item


# --------------------------------------------------------------------------- #
# Posts  /api/posts
# --------------------------------------------------------------------------- #
posts_router = APIRouter(prefix="/posts", tags=["posts"])


@posts_router.get("/", response_model=list[PostOut])
def list_posts(
    status_filter: PostStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Post).order_by(Post.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(Post.status == status_filter)
    return db.execute(stmt).scalars().all()


@posts_router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: str, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


@posts_router.post("/{post_id}/publish", response_model=SimpleMessage)
def republish_post(post_id: str, db: Session = Depends(get_db)):
    if not db.get(Post, post_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    from app.tasks import publish_post_task

    publish_post_task.delay(post_id)
    return SimpleMessage(detail="publication enqueued")


# --------------------------------------------------------------------------- #
# Manual generation  /api/generate
# --------------------------------------------------------------------------- #
generate_router = APIRouter(prefix="/generate", tags=["generation"])


@generate_router.post("/", response_model=GenerateResponse)
def manual_generate(payload: GenerateRequest, db: Session = Depends(get_db)):
    news = db.get(NewsItem, payload.news_id) if payload.news_id else None
    if payload.news_id and not news:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "news_id not found")

    gen_input = GenerationInput(
        title=payload.title or (news.title if news else None),
        summary=payload.summary or (news.summary if news else None),
        raw_text=payload.raw_text or (news.raw_text if news else None),
        url=payload.url or (news.url if news else None),
        source=payload.source or (news.source if news else None),
    )

    try:
        text = ai_generate_post(gen_input, model=payload.model)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI provider error: {exc}")

    post_id = None
    if payload.persist:
        post = Post(
            news_id=news.id if news else None,
            generated_text=text,
            status=PostStatus.generated,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id
        if payload.publish:
            from app.tasks import publish_post_task

            publish_post_task.delay(post_id)

    return GenerateResponse(
        generated_text=text,
        post_id=post_id,
        used_offline_stub=not settings.openai_enabled,
    )


# --------------------------------------------------------------------------- #
# Error logs  /api/logs
# --------------------------------------------------------------------------- #
logs_router = APIRouter(prefix="/logs", tags=["logs"])


@logs_router.get("/", response_model=list[ErrorLogOut])
def list_logs(
    scope: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
    if scope:
        stmt = stmt.where(ErrorLog.scope == scope)
    return db.execute(stmt).scalars().all()


# --------------------------------------------------------------------------- #
# Ops  /api/collect  (manual full run)
# --------------------------------------------------------------------------- #
ops_router = APIRouter(prefix="/collect", tags=["ops"])


@ops_router.post("/", response_model=SimpleMessage)
def trigger_collect():
    from app.tasks import collect_all_sources

    collect_all_sources.delay()
    return SimpleMessage(detail="collection enqueued")


ALL_ROUTERS = [
    sources_router,
    keywords_router,
    news_router,
    posts_router,
    generate_router,
    logs_router,
    ops_router,
]
