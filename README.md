# AI-генератор постов для Telegram (Project M4)

Сервис собирает новости с сайтов и из публичных Telegram-каналов, фильтрует их,
генерирует лаконичные посты через OpenAI GPT-4 и публикует их в Telegram-канал
по расписанию. Управление источниками, ключевыми словами, просмотр истории и
логов — через REST API (FastAPI + Swagger).

## Архитектура

```
Celery Beat ──(каждые 30 мин)──> collect_all_sources
                                      │  fan-out по включённым источникам
                                      ▼
                                 parse_source ──> [ParsedNews...]
                                      │  фильтр: дубли / язык / ключевые слова
                                      ▼
                            NewsItem + Post(new)
                                      ▼
                              generate_post_task ──(OpenAI GPT-4)──> Post(generated)
                                      ▼
                              publish_post_task ──(Telethon)──> Telegram-канал
                                      ▼
                                 Post(published | failed)
```

- **FastAPI** — REST API + автодокументация `/docs`.
- **Celery** — очередь задач; брокер **RabbitMQ**, result backend **Redis**.
- **PostgreSQL** — хранение `NewsItem`, `Post`, `Source`, `Keyword`, `ErrorLog`.
- **Redis** — быстрый кэш дедупликации (`aibot:seen_news`).
- **OpenAI** — генерация постов (`app/ai`). Без ключа используется офлайн-заглушка,
  чтобы пайплайн оставался рабочим.
- **Telethon** — чтение публичных каналов (`app/news_parser/telegram.py`) и
  публикация (`app/telegram/publisher.py`).

## Структура

```
aibot/
├── app/
│   ├── main.py               FastAPI-приложение, lifespan, роутеры
│   ├── config.py             Pydantic Settings (.env)
│   ├── database.py           engine / SessionLocal / Base / init_db
│   ├── models.py             ORM: NewsItem, Post, Source, Keyword, ErrorLog
│   ├── filters.py            дедуп + язык + ключевые слова
│   ├── errors.py             запись ErrorLog
│   ├── utils.py              логирование, хэш id, Redis-дедуп, определение языка
│   ├── celery_app.py         Celery + Beat schedule
│   ├── tasks.py              цепочка parse → filter → generate → publish
│   ├── api/
│   │   ├── endpoints.py      /sources /keywords /news /posts /generate /logs /collect
│   │   └── schemas.py        Pydantic-схемы запросов/ответов
│   ├── news_parser/
│   │   ├── base.py           ParsedNews
│   │   ├── sites.py          RSS/Atom + fallback по метатегам
│   │   └── telegram.py       Telethon-парсер публичных каналов
│   ├── ai/
│   │   ├── openai_client.py  обёртка Chat Completions + обработка ошибок
│   │   └── generator.py      промпт + офлайн-заглушка
│   └── telegram/
│       ├── bot.py            фабрика TelegramClient + интерактивный логин
│       └── publisher.py      публикация текста в целевой канал
├── celery_worker.py          точка входа worker / beat
├── scripts/telethon_login.py разовый логин Telethon (создаёт .session)
├── tests/                    smoke-тесты API (SQLite, без внешних сервисов)
├── docker-compose.yml        postgres + rabbitmq + redis + api + worker + beat
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Запуск через Docker

```bash
cp .env.example .env          # впишите OPENAI_API_KEY и TELEGRAM_* при необходимости
docker compose up --build
```

- API + Swagger: http://localhost:8000/docs
- RabbitMQ UI: http://localhost:15672 (guest / guest)

Таблицы создаются автоматически при старте API (`init_db()` → `create_all`).
Для продакшена можно подключить Alembic (пакет уже в `requirements.txt`).

## Локальный запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# упрощённо: DATABASE_URL=sqlite:///./aibot.db  (Celery всё равно нужен брокер)

uvicorn app.main:app --reload
celery -A celery_worker.celery_app worker -l info
celery -A celery_worker.celery_app beat -l info
```

### Telethon
Публикация и чтение TG-каналов требуют разовой авторизации сессии:

```bash
python scripts/telethon_login.py     # спросит телефон + код
```

Файл `aibot.session` переиспользуется worker'ом. Без заполненных
`TELEGRAM_API_ID/HASH/TARGET_CHANNEL` публикация помечается как `skipped`,
а пост остаётся в статусе `generated`.

## API

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET/POST | `/api/sources/` | список / создание источника |
| GET/PATCH/DELETE | `/api/sources/{id}` | чтение / изменение / удаление |
| POST | `/api/sources/{id}/parse` | запустить парсинг источника сейчас |
| GET/POST | `/api/keywords/` | список / добавление ключевого слова |
| DELETE | `/api/keywords/{id}` | удаление ключевого слова |
| GET | `/api/news/` | новости (фильтр `source`, `limit`, `offset`) |
| GET | `/api/posts/` | история постов (фильтр `status`) |
| GET | `/api/posts/{id}` | один пост |
| POST | `/api/posts/{id}/publish` | повторная публикация |
| POST | `/api/generate/` | ручная генерация поста (см. ниже) |
| GET | `/api/logs/` | лог ошибок (`ErrorLog`) |
| POST | `/api/collect/` | запустить полный сбор по всем источникам |
| GET | `/docs` | Swagger UI |

### Примеры запросов

Добавить источник-сайт (RSS):

```bash
curl -X POST localhost:8000/api/sources/ -H 'Content-Type: application/json' -d '{
  "type": "site", "name": "Хабр — лучшее", "url": "https://habr.com/ru/rss/best/"
}'
```

Добавить источник — Telegram-канал:

```bash
curl -X POST localhost:8000/api/sources/ -H 'Content-Type: application/json' -d '{
  "type": "tg", "name": "Дуров", "url": "durov"
}'
```

Добавить ключевое слово для фильтра:

```bash
curl -X POST localhost:8000/api/keywords/ -H 'Content-Type: application/json' -d '{"word": "AI"}'
```

Запустить полный сбор новостей вручную (не дожидаясь Beat):

```bash
curl -X POST localhost:8000/api/collect/
```

Ручная генерация поста:

```bash
curl -X POST localhost:8000/api/generate/ -H 'Content-Type: application/json' -d '{
  "title": "Учёные открыли новый вид глубоководных рыб",
  "summary": "Экспедиция нашла рыбу на глубине 8000 м.",
  "url": "https://example.com/fish",
  "persist": true,
  "publish": false
}'
# -> {"generated_text": "🐟 ...", "post_id": "…", "used_offline_stub": false}
```

`news_id` можно передать вместо текста — данные возьмутся из сохранённой новости.

Посмотреть историю постов и лог ошибок:

```bash
curl "localhost:8000/api/posts/?status=published&limit=20"
curl "localhost:8000/api/logs/?limit=50"
```

Опубликовать сгенерированный пост повторно:

```bash
curl -X POST localhost:8000/api/posts/<POST_ID>/publish
```

## Фильтрация

Перед генерацией `app/filters.py` отсеивает:
- **дубли** — по детерминированному `sha256(source + url|title)` (PK `NewsItem` + Redis-сет);
- **язык** — `FILTER_LANGUAGES` (по умолчанию `ru`, `en`);
- **ключевые слова** — таблица `keywords`; режим `KEYWORD_MATCH_MODE` = `any`/`all`;
  пустой список ⇒ пропускаются все.

## Обработка ошибок AI

`app/ai/openai_client.py` разделяет `RateLimitError` → `AIRateLimitError`
(таск повторяется с нарастающей задержкой до 10 мин) и недоступность API
→ `AIUnavailableError` (фолбэк на офлайн-заглушку). Прочие сбои → пост в
статус `failed` + запись в `ErrorLog`.

## Тесты

```bash
pytest
```

Smoke-набор проверяет CRUD источников/ключевых слов и ручную генерацию на
SQLite без RabbitMQ/Redis/OpenAI.

## Чеклист

| № | Функция | Реализация |
|---|---------|-----------|
| 1 | Сбор новостей (сайты) | `news_parser/sites.py`, `tasks.parse_source`, Beat 30 мин |
| 2 | Сбор новостей (Telegram) | `news_parser/telegram.py` (Telethon) |
| 3 | Фильтрация новостей | `filters.py` (дубли/язык/ключевые слова, Redis) |
| 4 | AI-генерация постов | `ai/openai_client.py`, `ai/generator.py`, `tasks.generate_post_task` |
| 5 | Публикация в Telegram | `telegram/publisher.py`, `tasks.publish_post_task` |
| 6 | API-управление источниками | `/api/sources/` CRUD |
| 7 | API-фильтры (ключевые слова) | `/api/keywords/` CRUD |
| 8 | История постов | `/api/posts/` GET |
| 9 | Генерация вручную | `/api/generate/` POST |
| 10 | Документация API | `/docs` (Swagger, FastAPI) |
| 11 | Логирование | `logging` + `ErrorLog` + `/api/logs/` |
