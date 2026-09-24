# Deployment (Docker)

The repository ships a production stack for Docker Compose: PostgreSQL, Valkey, Ollama, the API,
the worker and nginx, plus optional overrides for NVIDIA GPUs and automatic HTTPS.

## Prerequisites

- Docker Engine 24+ with **Compose v2.24+** (the TLS override uses `!reset`)
- For GPU acceleration: an NVIDIA GPU, a current driver and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- For automatic HTTPS: a DNS name pointing to the server, ports 80 and 443 open
- Outbound internet access on first start to download the LLM (Ollama registry) and the Whisper
  model (Hugging Face) — or pre-seeded model volumes, see *Offline installations*

### Sizing

| Setup | LLM | Whisper | Needs | Speed (1 h lecture) |
|---|---|---|---|---|
| GPU (recommended) | `gemma3:12b` | `large-v3-turbo` | ~16 GB VRAM for both, 16 GB RAM | a few minutes |
| Small GPU | `gemma3:4b` / `llama3.1:8b` | `small` | 8 GB VRAM | a few minutes |
| CPU only | `llama3.2:3b` | `small` | 8+ cores, 16 GB RAM | 20–40 min |

Transcription needs about 0.3 GB RAM per hour of audio on top of the model.

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
4. Open `PUBLIC_ORIGIN` and register — or create accounts yourself when registration is closed:

```bash
docker compose exec api python -m sonora.cli create-user --email you@example.com --name "Your Name" --plan pro
```

Check the stack: `docker compose ps` (all healthy), `docker compose exec api python -m sonora.cli check-llm`.

### Trying it locally

`PUBLIC_HOST=localhost`, `PUBLIC_ORIGIN=http://localhost:8080`, then
`docker compose up -d --build` and open <http://localhost:8080>. Browsers accept the
`Secure` session cookie on `localhost` even without TLS.

## Configuration

`.env` (see `.env.example`) feeds `docker-compose.yml`, which maps it onto the backend's
`SONORA_*` settings (documented in `Backend/sonora/config.py`). Frequently changed values:

| Variable | Effect |
|---|---|
| `LLM_MODEL`, `LLM_CONTEXT_TOKENS` | Model and context window (Ollama is started with the same context length) |
| `WHISPER_MODEL`, `WHISPER_DEVICE` | Speech model; `auto` uses the GPU when available |
| `REGISTRATION_ENABLED`, `DEFAULT_PLAN` | Who can sign up and which quota they get |
| `MAX_UPLOAD_MB`, `MAX_AUDIO_MINUTES` | Upload limits (applied to nginx and the API) |
| `API_WORKERS` | API processes (rate limits are shared through Valkey) |
| `HSTS_ENABLED` | HSTS from the API (the TLS override enables it) |
| `OLLAMA_IMAGE` | Pin an Ollama release for reproducible deployments |

Using a reasoning model such as `qwen3`? Add `SONORA_LLM_THINK: "false"` to the backend
environment so it answers directly instead of spending tokens on "thinking".

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
starts:

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
| Sessions fail with "Analysis failed" | The LLM is unreachable, too slow (`LLM_TIMEOUT_SECONDS`) or out of memory: `docker compose logs ollama` |
| Uploads fail with 413 | `MAX_UPLOAD_MB` (applies to nginx and the API) |
| GPU not used | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml ...` and `nvidia-smi` inside the container |
