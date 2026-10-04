# Deployment (Docker)

The repository ships a production stack for Docker Compose: PostgreSQL, Valkey, Ollama, the API,
the worker and nginx, plus optional overrides for NVIDIA GPUs and automatic HTTPS.

## Prerequisites

- Docker Engine 24+ with **Compose v2.24+** (optional `env_file`, and `!reset` in the TLS override)
- For GPU acceleration: an NVIDIA GPU, a current driver and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- For automatic HTTPS: a DNS name pointing to the server, ports 80 and 443 open
- Outbound internet access on first start to download the LLM (Ollama registry) and the Whisper
  model (Hugging Face) — or pre-seeded model volumes, see *Offline installations*

### Sizing

| Setup | LLM | Whisper | Needs |
|---|---|---|---|
| GPU (recommended) | `qwen3.5:9b`, 32K context | `large-v3-turbo` | ~16 GB VRAM for both, 16 GB RAM |
| Small GPU | `qwen3.5:9b`, 16K context | `small` | 8 GB VRAM (the model runs partly on the CPU) |
| Large GPU | `qwen3.5:27b`, 32K context | `large-v3-turbo` | 24 GB+ VRAM |
| CPU only | `qwen3.5:9b` or `qwen3.5:4b`, 16K context | `small` | 8+ cores, 16 GB RAM; expect long processing times |

Measured on the small-GPU setup (8 GB RTX 2080, `qwen3.5:9b`, 16K context): recap and quiz
of a 29-minute lecture took 95 s, the lecture analysis (topics + three score judgements)
another 64 s.

Transcription needs about 0.3 GB RAM per hour of audio on top of the model.

Links that share the chatbot add GPU load while a lecture runs: Ollama answers
`OLLAMA_NUM_PARALLEL` requests at a time and queues the rest. Each API process therefore
generates at most four listener answers at once and tells further listeners that the
assistant is busy, so processing and the owner's chat aren't starved (on the small-GPU setup,
the first answer took 11 s including loading the model).

## First start

```bash
cp .env.example .env
# edit .env: PUBLIC_HOST, PUBLIC_ORIGIN, POSTGRES_PASSWORD (openssl rand -base64 36), models
chmod 600 .env

# CPU only, plain HTTP on :8080 (behind your own TLS proxy):
docker compose up -d --build

# GPU + automatic HTTPS via Caddy/Let's Encrypt:
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.tls.yml up -d --build
```

What happens:

1. `db` and `valkey` start; `migrate` runs `alembic upgrade head` and exits.
2. `ollama` starts; `ollama-pull` downloads `LLM_MODEL` once (follow with
   `docker compose logs -f ollama-pull`; several GB).
3. `api`, `worker` and `web` start. The Whisper model is downloaded on the first transcription
   into the `whisper-models` volume.
4. Open `PUBLIC_ORIGIN` and register. New accounts start on the Free plan (one session a
   month, recordings up to 60 minutes) and can buy Trainer or Pro in the simulated checkout
   (test card `4242 4242 4242 4242`; no money moves). Or create accounts with a plan yourself
   (also when registration is closed):

```bash
docker compose exec api python -m sonora.cli create-user --email you@example.com --name "Your Name" --plan pro
```

Check the stack: `docker compose ps` (all healthy), `docker compose exec api python -m sonora.cli check-llm`.

### Trying it locally

In `.env`: `PUBLIC_HOST=localhost`, `PUBLIC_ORIGIN=http://localhost:8080` and
`HTTP_PORT=127.0.0.1:8080` (reachable from this machine only); on a GPU with 8 GB also
`LLM_CONTEXT_TOKENS=16384`, `OLLAMA_NUM_PARALLEL=1` and `WHISPER_MODEL=small` (see *Sizing*).
Then `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build` (without
the GPU file on a CPU-only machine) and open <http://localhost:8080> — exactly this address:
the host allow-list rejects `127.0.0.1`. Browsers accept the `Secure` session cookie on
`localhost` even without TLS. To test a share link as a listener, open it in a private window
or another browser (see the README, *Testing share links as a listener*).

## Configuration

Every backend setting is named `SONORA_<NAME>` and documented in `Backend/sonora/config.py`.
In the Docker stack a setting gets its value from the first of these that sets it:

1. **`docker-compose.yml`.** It fixes what the stack depends on or what must stay secure in
   production, and it maps the short names from `.env` (`LLM_MODEL` → `SONORA_LLM_MODEL`).
2. **`.env`** (template: `.env.example`). Besides the short names it can hold any other
   backend setting under its `SONORA_` name; Compose passes the file to `api`, `worker` and
   `migrate`. A `SONORA_` line has no effect on a setting that `docker-compose.yml` sets —
   use the short name for those.
3. **The default in `config.py`.** It targets a development machine.

So Docker overrides these code defaults:

| Setting | `config.py` | Docker |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` (startup refuses unsafe settings, API docs off) |
| `DATABASE_URL` | SQLite file | the `db` PostgreSQL service |
| `ALLOWED_HOSTS` / `ALLOWED_ORIGINS` | `*` / Vite dev server | `PUBLIC_HOST`,`localhost` / `PUBLIC_ORIGIN` |
| `RATE_LIMIT_STORAGE_URL` | `memory://` (per process) | Valkey (shared by all API processes) |
| `STORAGE_DIR` / `WHISPER_MODEL_DIR` | `./data` / Hugging Face cache | the `audio-data` / `whisper-models` volumes |
| `WORKER_EMBEDDED` | `true` | `false` (the separate `worker` container) |
| `LOG_JSON` | `false` | `true` |
| `LLM_BASE_URL` | `http://localhost:11434` | the `ollama` service |
| `LLM_CONTEXT_TOKENS` | `16384` | `32768` (`LLM_CONTEXT_TOKENS`) |
| `LLM_TIMEOUT_SECONDS` | `600` | `900` (`LLM_TIMEOUT_SECONDS`) |
| `WHISPER_MODEL` | `small` | `large-v3-turbo` (`WHISPER_MODEL`) |
| `WHISPER_DEVICE` | `auto` | `cuda` with `docker-compose.gpu.yml` |
| `HSTS_ENABLED` | `false` | `true` with `docker-compose.tls.yml` |

The other short names default to the code's values, and every setting not listed keeps its
code default unless `.env` sets it. `Backend/tests/unit/test_deployment_files.py` fails when
the compose files or templates name a setting that doesn't exist, miss one, show a wrong
default, or let Docker differ from `config.py` anywhere but in the rows above.

Frequently changed values:

| Variable | Effect |
|---|---|
| `LLM_MODEL`, `LLM_CONTEXT_TOKENS` | Model and context window (Ollama is started with the same context length) |
| `WHISPER_MODEL`, `WHISPER_DEVICE` | Speech model; `auto` uses the GPU when available |
| `REGISTRATION_ENABLED`, `DEFAULT_PLAN` | Who can sign up, and the plan of new accounts (`free` = one session a month, the default; `none` = no free tier, a plan must be bought; `trainer`/`pro` give it to everyone for free) |
| `MAX_UPLOAD_MB`, `MAX_AUDIO_MINUTES` | Upload limits (applied to nginx and the API) |
| `API_WORKERS` | API processes (rate limits are shared through Valkey) |
| `HSTS_ENABLED` | HSTS from the API (the TLS override enables it) |
| `OLLAMA_IMAGE` | Pin an Ollama release for reproducible deployments |

All further settings are in `.env.example`, commented out with their default and a short
explanation: uncomment a line and change its value. Two of them can't be changed in
production: the API refuses to start with `SONORA_RATE_LIMIT_ENABLED=false` (it would also
lift the sign-in lockout) or `SONORA_DATABASE_ECHO=true` (it would log personal data).

Deliberately not configurable: the per-task sampling, prompts and output limits
(`Backend/sonora/ai/`), the rate limits (`Backend/sonora/api/routes/`), the plan catalog with
its prices (`Backend/sonora/plans.py`) and the feedback form (`Backend/sonora/feedback.py`).
The frontend shows prices and limits only as the API's `/meta` reports them.

## Behind your own reverse proxy

Run without the TLS override and point your proxy at the `web` container port (`HTTP_PORT`).
The proxy must pass the original `Host` header and set `X-Forwarded-For`. Tell nginx which
address the proxy connects from, otherwise every client appears as the proxy (rate limits
would then apply to everyone together):

```bash
TRUSTED_PROXY_CIDR=10.0.0.5/32   # the proxy's address as seen by the web container
```

Never set it to a range that untrusted clients can connect from — they could then spoof their
IP address.

## Operations

**Logs** — JSON lines from the API and worker, nginx access log with redacted share tokens:

```bash
docker compose logs -f api worker web
```

**Backups** — the database holds everything except audio that is still waiting for
transcription:

```bash
docker compose exec -T db pg_dump -U sonora -Fc sonora > sonora-$(date +%F).dump
# restore into an empty database:
docker compose exec -T db pg_restore -U sonora -d sonora --clean --if-exists < sonora-2026-09-24.dump
```

**Upgrades** — pull the new version and rebuild; migrations run automatically before the API
starts (when changing `LLM_MODEL`, the `ollama-pull` service downloads the new model first):

```bash
git pull
docker compose up -d --build
```

**Scaling** — more API processes with `API_WORKERS`; more parallel processing with
`docker compose up -d --scale worker=2` (each worker loads its own Whisper model). Jobs are
claimed safely by multiple workers.

**Maintenance** — expired sign-ins, dead jobs, old job records and orphaned audio are cleaned
up by the worker every 10 minutes (`python -m sonora.cli maintenance` runs it once).

## Offline installations / blocked model hosts

- **LLM**: copy an existing Ollama model directory into the `ollama-models` volume, or run
  `ollama pull` on a connected machine and transfer `~/.ollama/models`.
- **Whisper**: download the model files (see `Backend/README.md`, *Speech-to-text models*) into
  the `whisper-models` volume, e.g. `/models/faster-whisper-large-v3-turbo`, and set
  `WHISPER_MODEL=/models/faster-whisper-large-v3-turbo`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `api` restarts with "Unsafe production configuration" | The message lists the setting — usually `PUBLIC_HOST`/`PUBLIC_ORIGIN` |
| Sign-in works, next request says "session expired" | The site is served over plain HTTP from a non-localhost address; the `Secure` cookie is not stored → use HTTPS |
| `403 origin_not_allowed` on every action | `PUBLIC_ORIGIN` doesn't match the address in the browser (scheme, host and port must match) |
| Sessions stay `queued` | `docker compose logs worker`; the worker waits for Ollama to be healthy |
| Sessions fail with "Processing failed" | The LLM is unreachable, too slow (`LLM_TIMEOUT_SECONDS`) or out of memory: `docker compose logs ollama` |
| The Analysis tab says "The analysis failed" | Same causes as above; the lecturer can retry from the tab. Script and quiz are unaffected |
| Listeners behind one network get `429` | Many listeners share one IP (lecture hall NAT); the public limits allow 600 page loads per minute per IP (`Backend/sonora/api/routes/public.py`) |
| Uploads fail with 413 | `MAX_UPLOAD_MB` (applies to nginx and the API) |
| GPU not used | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml ...` and `nvidia-smi` inside the container |
