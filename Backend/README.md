# Sonora — Backend

FastAPI service that stores recordings, runs speech-to-text and LLM generation in a
background worker, and serves the SPA's API under `/api/v1`.

- Python 3.12+ (3.13 in Docker), dependencies managed with [uv](https://docs.astral.sh/uv/)
- SQLite for local development, PostgreSQL in Docker/production — same models and migrations
- faster-whisper for transcription, Ollama for the LLM, both self-hosted

## Setup

```bash
uv sync --extra transcription     # dev tools + faster-whisper (omit the extra for API-only work)
cp .env.example .env              # local settings (git-ignored)
uv run alembic upgrade head       # create/upgrade the database
uv run python -m sonora.cli seed-demo   # optional demo trainer with 4 sample sessions
uv run uvicorn sonora.main:create_app --factory --reload
```

- API docs (development only): <http://127.0.0.1:8000/api/v1/docs>
- With `SONORA_WORKER_EMBEDDED=true` (the `.env.example` default) the worker runs inside the
  API process. To run it separately, set it to `false` and start `uv run python -m sonora.worker`.
- `uv run python -m sonora.cli check-llm` verifies that Ollama is reachable and has the model.

## Configuration

All settings are environment variables with the `SONORA_` prefix (or entries in `.env`) and
are defined, with defaults and comments, in [`sonora/config.py`](sonora/config.py). Defaults
are secure; `.env.example` relaxes only what local development needs. With
`SONORA_ENVIRONMENT=production` the app **refuses to start** with unsafe settings (insecure
cookies, `*` host allow-list, SQLite, the fake transcriber, missing origins).

| Setting | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/sonora.db` | `postgresql+asyncpg://…` in production |
| `ALLOWED_ORIGINS` | `http://localhost:5173,…` | Origins allowed to send state-changing requests |
| `ALLOWED_HOSTS` | `*` | Host header allow-list (required in production) |
| `COOKIE_SECURE` | `true` | `Secure` + `__Host-` session cookie; `false` only for plain-HTTP dev |
| `SESSION_TTL_HOURS` / `SESSION_IDLE_HOURS` | `336` / `72` | Absolute and inactivity session lifetime |
| `REGISTRATION_ENABLED` | `true` | Public sign-up |
| `PASSWORD_MIN_LENGTH` | `12` | Password policy |
| `DEFAULT_PLAN` | `trainer` | Plan for new accounts (`starter` 1, `trainer` 10, `pro` unlimited sessions/month) |
| `RATE_LIMIT_STORAGE_URL` | `memory://` | `async+valkey://host:6379` when running several API processes |
| `STORAGE_DIR` | `./data` | Uploaded audio (shared by API and worker) |
| `MAX_UPLOAD_MB` / `MAX_AUDIO_MINUTES` | `200` / `180` | Upload limits |
| `KEEP_AUDIO` | `false` | Keep audio after transcription (default: delete) |
| `LLM_BASE_URL` / `LLM_MODEL` | `http://localhost:11434` / `llama3.2:3b` | Ollama server and model |
| `LLM_CONTEXT_TOKENS` | `8192` | Context window requested per call (transcripts beyond it are condensed first) |
| `LLM_THINK` | unset | `false` disables "thinking" on reasoning models (e.g. qwen3) |
| `TRANSCRIPTION_BACKEND` | `faster-whisper` | `fake` returns a sample transcript (development only) |
| `WHISPER_MODEL` | `small` | Model name or path to a local model folder |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `auto` / `default` | `cuda` + `float16` on GPU, `cpu` + `int8` otherwise |
| `WORKER_EMBEDDED` | `true` | Run the worker inside the API process |
| `JOB_MAX_ATTEMPTS` / `JOB_LEASE_SECONDS` | `3` / `300` | Retry budget and crash-recovery lease |
| `DOCS_ENABLED` | on outside production | Swagger UI at `/api/v1/docs` |
| `LOG_JSON` | `false` | JSON log lines (production) |

## Project structure

```
sonora/
├── main.py            # app factory: middleware, routes, lifespan (embedded worker)
├── config.py          # settings + production safety checks
├── container.py       # Services: engine, sessionmaker, hasher, rate limiter, storage, LLM
├── security.py        # tokens, Argon2id hashing, password policy
├── ratelimit.py       # moving-window rate limiter (memory / Valkey)
├── storage.py         # streamed uploads, magic-byte detection, safe file keys
├── errors.py          # error types and the JSON error envelope
├── api/               # HTTP layer: schemas, dependencies (auth, CSRF), middleware, routes/
├── services/          # business logic: auth, account, sessions, shares, quiz, chat, activity
├── models/            # SQLAlchemy models
├── db/                # base, UTC datetime type, engine/session factories
├── ai/                # Ollama client, prompts, generation, chat, BM25 retrieval, timestamps
├── transcription/     # Transcriber protocol, faster-whisper adapter, dev fake
├── worker/            # job queue, processing pipeline, worker loop, `python -m sonora.worker`
├── demo/              # sample sessions for `seed-demo` and the fake transcriber
└── cli.py             # admin commands
migrations/            # Alembic (async; SQLite batch mode)
tests/                 # unit/, api/, worker/, integration/ (+ migrations, CLI, lifecycle)
```

Route handlers are thin: they validate input with Pydantic schemas and call a service; services
own transactions. No route or service reads settings or clients from globals — everything comes
from the `Services` container on `app.state`, which is how tests swap in fakes.

## API

JSON everywhere except the audio upload. Errors always look like
`{"error": {"code": "email_taken", "message": "…", "details": […]}}`; clients branch on `code`.

**Authentication.** Signing in sets an `HttpOnly` session cookie and returns a `csrf_token`.
Every `POST`/`PATCH`/`DELETE` of a signed-in user must send it in the `X-CSRF-Token` header.
`GET /auth/me` returns it again after a page reload.

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health`, `/health/ready` | public | Liveness; readiness (database) |
| GET | `/meta` | public | Limits, languages, feature switches for the client |
| POST | `/auth/register` | public, 5/h per IP | Create account and sign in |
| POST | `/auth/login` | public, lockout | Sign in |
| POST | `/auth/logout` | session | Sign out (server-side) |
| GET | `/auth/me` | session | Current user + CSRF token |
| PATCH | `/me` | session | Name, bio, notifications; email change needs `current_password` |
| POST | `/me/password` | session | Change password (signs out other devices) |
| POST | `/me/delete` | session | Delete account and all data (needs password) |
| GET | `/me/usage`, `/me/stats`, `/me/activity` | session | Plan & quota, totals, activity log |
| GET | `/sessions` | session | List sessions (newest first, `limit`/`offset`) |
| POST | `/sessions?title=&language=` | session | Upload audio as the **raw request body** → `202 queued` |
| GET | `/sessions/{id}` | owner | Status, script, quiz (without answers), transcript |
| DELETE | `/sessions/{id}` | owner | Delete session, shares, chat, audio |
| POST | `/sessions/{id}/retry` | owner | Re-queue a failed session |
| POST | `/sessions/{id}/quiz/check` | owner | Grade answers server-side |
| GET, POST | `/sessions/{id}/chat` | owner | Chat history / ask a question |
| GET, POST | `/sessions/{id}/shares` | owner | List / create participant links |
| DELETE | `/sessions/{id}/shares/{share_id}` | owner | Revoke a link |
| GET | `/public/shares/{token}` | link holder | Shared tabs only |
| POST | `/public/shares/{token}/quiz/check` | link holder | Grade a shared quiz |

All paths are prefixed with `/api/v1`. The OpenAPI schema is at `/api/v1/openapi.json`
(development). Foreign or unknown ids return `404` — the API never reveals that another
user's session exists.

**Why a raw-body upload?** FastAPI parses multipart bodies *before* dependencies run, so a
multipart endpoint would accept up to 200 MB from anyone before checking the session. With a
raw body, authentication, CSRF, rate limit and quota are checked first, and the stream goes
straight to disk with the size limit enforced while reading.

## Processing pipeline

```
queued → transcribing → generating → ready
   ↑            └──────────┴──→ failed (permanent) ─┐
   └─────────── retry with backoff (transient) ◄────┘ POST /retry
```

1. **Upload** — bytes are streamed to `STORAGE_DIR/audio/<random>.<ext>`; the format is detected
   from magic bytes (WebM, Ogg, MP3, M4A, WAV, FLAC, AAC). A job is queued in the same
   transaction as the session.
2. **Transcribe** (worker) — duration is probed without decoding (rejects over-long audio before
   using memory), then faster-whisper transcribes with voice-activity filtering. The transcript
   is saved and the **audio deleted** (unless `KEEP_AUDIO`).
3. **Generate** — the transcript goes to the LLM with JSON-schema-constrained output. Transcripts
   longer than the context window are first condensed into timestamped notes (map-reduce).
   Output is validated: timestamps are snapped to real segments, quiz options are built from
   `correct_answer` + `wrong_answers`, de-duplicated and shuffled server-side.
4. **Failures** — bad audio / no speech / too long fail permanently with a user-facing message;
   LLM outages and malformed output are retried (30 s, 2 min, 8 min…), then fail. A crashed
   worker's job is picked up again when its lease expires.

The queue is a database table (`jobs`) claimed with optimistic `UPDATE … WHERE status = …`, so
it needs no extra infrastructure and works identically on SQLite and PostgreSQL. Maintenance
(expired sign-ins, dead jobs, old job rows, orphaned audio files) runs in the worker every
10 minutes, or on demand with `python -m sonora.cli maintenance`.

## LLM

`llama3.2:3b` is enough to exercise every feature locally (a 40-minute sample takes ~4–5 min on
a laptop CPU). For production use a stronger model (see `.env.example` in the repository root).
Prompts live in [`sonora/ai/prompts.py`](sonora/ai/prompts.py); every prompt fences the
transcript as data because anything said in the room ends up in the prompt.

## Speech-to-text models

`SONORA_WHISPER_MODEL` accepts a faster-whisper model name (`tiny` … `large-v3`,
`large-v3-turbo`), downloaded from Hugging Face on first use, **or a path to a local model
folder**. Use a local folder when Hugging Face is not reachable (offline servers, corporate
proxies that block it):

1. From a machine that may access it, download `config.json`, `model.bin`, `tokenizer.json`
   and `vocabulary.txt` (plus `preprocessor_config.json` for large-v3 models) from
   <https://huggingface.co/Systran/faster-whisper-small> (or another `Systran/faster-whisper-*`
   repository).
2. Put them into e.g. `Backend/data/models/faster-whisper-small/` (git-ignored).
3. Set `SONORA_TRANSCRIPTION_BACKEND=faster-whisper` and
   `SONORA_WHISPER_MODEL=./data/models/faster-whisper-small` in `.env`.

Model size vs. speed on CPU: `base` is fast but weak for German, `small` is a good default,
`medium`/`large-v3-turbo` need a GPU to be practical.

## CLI

```bash
uv run python -m sonora.cli create-user --email ada@example.com --name "Ada" [--plan pro]  # prompts for the password
uv run python -m sonora.cli set-plan --email ada@example.com --plan pro
uv run python -m sonora.cli seed-demo            # refuses to run in production without --force
uv run python -m sonora.cli maintenance
uv run python -m sonora.cli check-llm
```

In Docker: `docker compose exec api python -m sonora.cli <command>`.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"   # then review the file!
uv run alembic upgrade head
uv run alembic check      # fails if models and migrations disagree (also enforced by the tests)
```

SQLite migrations run in batch mode (table rebuilds) with foreign keys *not* enforced during the
migration, so `ON DELETE CASCADE` can't delete rows while a table is rebuilt.

## Testing

```bash
uv run pytest --cov              # all offline tests + coverage (fails below 90 %)
uv run pytest tests/api -q       # one area
uv run pytest -m integration     # real Ollama (IT_OLLAMA_URL, IT_OLLAMA_MODEL) and optionally
                                 # real Whisper (IT_WHISPER_MODEL=<model or folder>, IT_AUDIO_FILE=<speech file>)
uv run ruff format --check . && uv run ruff check . && uv run mypy
```

- `tests/unit` — pure logic: security primitives, password policy, timestamps, retrieval,
  generation/validation, Ollama client (mock transport), storage, rate limiting, config.
- `tests/api` — HTTP behaviour end to end through the ASGI app with a fresh SQLite database per
  test: auth flows, CSRF, ownership isolation, uploads, quotas, sharing, chat, security headers,
  race conditions.
- `tests/worker` — queue claiming and leases, pipeline failure modes, retries, maintenance.
- `tests/test_migrations.py` — Alembic history builds exactly the models' schema.
- The LLM and transcriber are replaced by fakes (`tests/fakes.py`); nothing needs network access.
  Settings never come from your shell or `.env` during tests.

## Troubleshooting

- **`invalid peer certificate: UnknownIssuer` from uv behind a TLS-inspecting proxy** — use the
  OS certificate store: `UV_SYSTEM_CERTS=1 uv sync` (and unset `SSL_CERT_FILE` if it points at a
  single proxy CA).
- **Hugging Face downloads fail / are blocked** — use a local model folder (see above).
- **`database is locked` on SQLite** — only one writer at a time; happens under heavy parallel
  load in development. Use PostgreSQL for anything beyond local testing.
- **Uploads stay `queued`** — no worker is running: set `SONORA_WORKER_EMBEDDED=true` or start
  `python -m sonora.worker`.
