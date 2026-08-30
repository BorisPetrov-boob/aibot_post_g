# Чек-лист реализации — Project M4: AI-генератор постов для Telegram

Легенда: ✅ реализовано · 🟡 реализовано в минимальном объёме (нужны внешние ключи для боевого запуска)

## Функциональные блоки

| № | Требование | Статус | Где в коде |
|---|-----------|:---:|-----------|
| 1 | Сбор новостей с **сайтов**, отдельный парсер | ✅ | `app/news_parser/sites.py` — RSS/Atom (`feedparser`) + fallback по мета-тегам |
| 2 | Сбор новостей из **Telegram-каналов** (Telethon), отдельный парсер | 🟡 | `app/news_parser/telegram.py` — чтение публичных каналов; нужен `TELEGRAM_API_ID/HASH` + `.session` |
| 3 | Запуск сбора **по расписанию каждые 30 мин** (Celery Beat) | ✅ | `app/celery_app.py` → `beat_schedule` `collect-news-every-30-min` |
| 4 | Поля новости: `title`, `url`, `summary`, `source`, `published_at`, `raw_text` | ✅ | `app/models.py::NewsItem` |
| 5 | **Celery** + брокер (**RabbitMQ**) + result backend (Redis) | ✅ | `app/celery_app.py`, `celery_worker.py`, `docker-compose.yml` |
| 6 | Фоновая цепочка **парсинг → фильтрация → генерация → публикация** | ✅ | `app/tasks.py`: `collect_all_sources` → `parse_source` → `generate_post_task` → `publish_post_task` |
| 7 | Все тяжёлые операции — в отдельных Celery-тасках | ✅ | `app/tasks.py` (5 задач) |
| 8 | **AI-генерация** через публичный API (OpenAI-совместимый) | ✅ | `app/ai/openai_client.py`, `app/ai/generator.py`; роутер nordrouter.com, модель `anthropic/claude-fable-5` |
| 9 | Промпт: «краткое, интересное описание + emoji + call to action» | ✅ | `app/config.py::DEFAULT_AI_PROMPT` (переопределяется `AI_SYSTEM_PROMPT`) |
| 10 | Обработка ошибок AI API (**rate limit**, недоступность) | ✅ | `openai_client.py` → `AIRateLimitError` / `AIUnavailableError`; ретраи с backoff в `generate_post_task` |
| 11 | Ручной тест генерации через API | ✅ | `POST /api/generate/` (`app/api/endpoints.py`) |
| 12 | Фильтрация по **ключевым словам, языку, источнику** | ✅ | `app/filters.py::evaluate` |
| 13 | Гибкая система фильтров (через API/настройки) | ✅ | `/api/keywords/` CRUD, `FILTER_LANGUAGES`, `KEYWORD_MATCH_MODE=any\|all` |
| 14 | Исключение **дублей** (title / url / контент) | ✅ | детерминированный `sha256(source + url\|title)` = PK `NewsItem` + Redis-сет `aibot:seen_news` (`app/utils.py`, `app/filters.py::is_duplicate`) |
| 15 | Публикация AI-поста в канал через **Telethon** | 🟡 | `app/telegram/publisher.py`; нужен авторизованный `.session` + `TELEGRAM_TARGET_CHANNEL` |
| 16 | Проверка, что пост не опубликован повторно | ✅ | `publish_post_task` — проверка `PostStatus.published` перед отправкой |
| 17 | Логирование успешных публикаций и ошибок | ✅ | `logging` + модель `ErrorLog` + `app/errors.py::record_error` |
| 18 | REST API: **CRUD источников** (сайты, TG-каналы) | ✅ | `/api/sources/` — GET/POST/PATCH/DELETE + `POST /{id}/parse` |
| 19 | API управления **ключевыми словами / фильтрами** | ✅ | `/api/keywords/` — GET/POST/DELETE |
| 20 | Эндпоинты **истории постов** и **логов ошибок** | ✅ | `GET /api/posts/`, `GET /api/posts/{id}`, `GET /api/logs/` |
| 21 | **Swagger** — автогенерация FastAPI `/docs` | ✅ | `app/main.py` (FastAPI), доступно на `/docs` и `/redoc` |

## Структура данных

| Модель | Требуемые поля | Статус | Примечание |
|--------|----------------|:---:|-----------|
| `NewsItem` | id, title, url?, summary, source, published_at, raw_text | ✅ | id = sha256-хэш; +`language`, `created_at` |
| `Post` | id, news_id, generated_text, published_at, status(new/generated/published/failed) | ✅ | +`error`, `tg_message_id`, `created_at` |
| `Source` | id, type(site/tg), name, url, enabled | ✅ | +`created_at`, уникальность `(type, url)` |
| `Keyword` | id, word | ✅ | +`created_at`, `word` уникально |
| `ErrorLog` | — | ✅ | доп. модель под требование «логи ошибок» |

## Чек-лист из ТЗ (раздел 5)

| № | Функция | URL / Команда | Статус |
|---|---------|---------------|:---:|
| 1 | Сбор новостей (сайты) | Celery Beat | ✅ |
| 2 | Сбор новостей (Telegram) | Celery Beat | 🟡 |
| 3 | Фильтрация новостей | — | ✅ |
| 4 | AI-генерация постов | Celery Task | ✅ |
| 5 | Публикация в Telegram | Celery Task | 🟡 |
| 6 | API-управление | `/api/sources/` (CRUD) | ✅ |
| 7 | API-фильтры | `/api/keywords/` (CRUD) | ✅ |
| 8 | История постов | `/api/posts/` (GET) | ✅ |
| 9 | Генерация вручную | `/api/generate/` (POST) | ✅ |
| 10 | Документация API | `/docs/` (GET) | ✅ |
| 11 | Логирование | — | ✅ |

## Тесты

- `tests/test_api.py` — 6 smoke-тестов (SQLite, без RabbitMQ/Redis/AI): CRUD источников, CRUD ключевых слов, ручная генерация (offline-заглушка), валидация. Запуск: `pytest` → `6 passed`.

## Что требует внешних ключей для боевого запуска

- **Telegram (Telethon)** — `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` c <https://my.telegram.org>, разовый `python scripts/telethon_login.py`, аккаунт-админ целевого канала. Код готов, проверяется после авторизации сессии.
- **AI** — уже подключено: OpenAI-совместимый роутер, ключ в `.env` (не в репозитории). Живая генерация через `/api/generate/` проверена.
