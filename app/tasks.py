"""Celery task pipeline: parse -> filter -> AI generate -> publish."""
from __future__ import annotations

from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from app.ai.generator import GenerationInput, generate_post as ai_generate_post
from app.ai.openai_client import AIError, AIRateLimitError
from app.celery_app import celery_app
from app.database import session_scope
from app.errors import record_error
from app.filters import evaluate, load_keywords
from app.models import NewsItem, Post, PostStatus, Source, SourceType
from app.news_parser.sites import parse_site
from app.news_parser.telegram import parse_telegram_channel
from app.telegram.publisher import publish_text
from app.utils import get_logger, mark_seen

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# 1. Scheduled fan-out
# --------------------------------------------------------------------------- #
@celery_app.task(name="app.tasks.collect_all_sources")
def collect_all_sources() -> dict:
    with session_scope() as db:
        source_ids = db.execute(
            select(Source.id).where(Source.enabled.is_(True))
        ).scalars().all()
    for sid in source_ids:
        parse_source.delay(sid)
    logger.info("Dispatched parsing for %d sources", len(source_ids))
    return {"dispatched": len(source_ids)}


# --------------------------------------------------------------------------- #
# 2. Per-source parsing + filtering
# --------------------------------------------------------------------------- #
@celery_app.task(name="app.tasks.parse_source", bind=True, max_retries=2, default_retry_delay=60)
def parse_source(self, source_id: str) -> dict:
    with session_scope() as db:
        source = db.get(Source, source_id)
        if not source or not source.enabled:
            return {"source_id": source_id, "skipped": "disabled_or_missing"}

        try:
            if source.type == SourceType.site:
                items = parse_site(source.url, source.name)
            else:
                items = parse_telegram_channel(source.url)
        except Exception as exc:  # noqa: BLE001
            record_error(db, "parse_source", str(exc), context=f"source={source.name}")
            db.commit()  # persist the log before Retry unwinds the session
            raise self.retry(exc=exc)

        keywords = load_keywords(db)
        created, skipped = 0, 0
        for item in items:
            decision = evaluate(item, db, keywords=keywords)
            if not decision.passed:
                skipped += 1
                logger.debug("Filtered out %r: %s", item.title[:60], decision.reason)
                continue

            news = NewsItem(**item.to_model_kwargs())
            db.add(news)
            db.flush()
            mark_seen(news.id)

            post = Post(news_id=news.id, status=PostStatus.new)
            db.add(post)
            db.flush()
            created += 1
            generate_post_task.delay(post.id)

        logger.info("%s: %d new, %d filtered", source.name, created, skipped)
        return {"source": source.name, "created": created, "skipped": skipped}


# --------------------------------------------------------------------------- #
# 3. AI generation
# --------------------------------------------------------------------------- #
@celery_app.task(
    name="app.tasks.generate_post_task",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def generate_post_task(self, post_id: str) -> dict:
    with session_scope() as db:
        post = db.get(Post, post_id)
        if not post:
            return {"post_id": post_id, "error": "post_not_found"}
        news = db.get(NewsItem, post.news_id) if post.news_id else None
        gen_input = GenerationInput(
            title=news.title if news else None,
            summary=news.summary if news else None,
            raw_text=news.raw_text if news else None,
            url=news.url if news else None,
            source=news.source if news else None,
        )

        try:
            text = ai_generate_post(gen_input)
        except AIRateLimitError as exc:
            logger.warning("Rate limited, retrying post %s", post_id)
            raise self.retry(exc=exc, countdown=min(60 * (self.request.retries + 1), 600))
        except (AIError, ValueError) as exc:
            post.status = PostStatus.failed
            post.error = str(exc)
            record_error(db, "generate_post", str(exc), context=f"post={post_id}")
            return {"post_id": post_id, "status": "failed", "error": str(exc)}

        post.generated_text = text
        post.status = PostStatus.generated
        post.error = None

    publish_post_task.delay(post_id)
    return {"post_id": post_id, "status": "generated"}


# --------------------------------------------------------------------------- #
# 4. Publication
# --------------------------------------------------------------------------- #
@celery_app.task(
    name="app.tasks.publish_post_task",
    bind=True,
    max_retries=3,
    default_retry_delay=45,
)
def publish_post_task(self, post_id: str) -> dict:
    with session_scope() as db:
        post = db.get(Post, post_id)
        if not post:
            return {"post_id": post_id, "error": "post_not_found"}
        if post.status == PostStatus.published:
            return {"post_id": post_id, "status": "already_published"}
        if not post.generated_text:
            post.status = PostStatus.failed
            post.error = "no_generated_text"
            return {"post_id": post_id, "status": "failed", "error": "no_generated_text"}

        result = publish_text(post.generated_text)

        if result.ok:
            post.status = PostStatus.published
            post.published_at = _utcnow()
            post.tg_message_id = result.message_id
            post.error = None
            return {"post_id": post_id, "status": "published", "message_id": result.message_id}

        if result.skipped:
            post.error = result.error
            logger.warning("Publish skipped for %s (%s)", post_id, result.error)
            return {"post_id": post_id, "status": "skipped", "error": result.error}

        post.status = PostStatus.failed
        post.error = result.error
        record_error(db, "publish_post", result.error or "unknown", context=f"post={post_id}")
        db.commit()  # persist status + log before Retry unwinds the session

    raise self.retry(countdown=45)


# --------------------------------------------------------------------------- #
# Convenience: run the whole chain for one already-stored news item
# --------------------------------------------------------------------------- #
@shared_task(name="app.tasks.process_news_item")
def process_news_item(news_id: str) -> dict:
    with session_scope() as db:
        news = db.get(NewsItem, news_id)
        if not news:
            return {"news_id": news_id, "error": "not_found"}
        post = Post(news_id=news_id, status=PostStatus.new)
        db.add(post)
        db.flush()
        pid = post.id
    generate_post_task.delay(pid)
    return {"news_id": news_id, "post_id": pid}
