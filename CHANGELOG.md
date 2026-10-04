# Changelog

## Unreleased

Aligns the backend with the reworked frontend (plans and checkout, QR codes, listener
feedback) and adds listener statistics and a lecture analysis.

### Added

- **Chat for listeners**: share links can include the chatbot (new `chat` tab, on by default
  in the share dialog; existing links keep their tabs). `POST /public/shares/{token}/chat`.
  Listeners' conversations are never stored: the page sends its last six turns with each
  question. Limits per listener (5/min, 60/day), per IP (300/h) and per lecture (600/h). Each
  API process generates at most four listener answers at once; further questions get
  `503 assistant_busy`. The owner can try the chat on their own link under their usual chat
  limits.
- **Free plan**: one session a month with recordings up to 60 minutes and every feature.
  New accounts start on it (`SONORA_DEFAULT_PLAN=free`, the new default; `none` turns the free
  tier off); cancelling a paid plan falls back to it, and accounts without a plan switch to it
  without payment (`POST /billing/checkout` with `"plan": "free"`, no token). Migration `0003`
  moves accounts of the former admin-only "starter" plan to it. Plans can limit the
  recording length (`max_audio_minutes`): the worker enforces it, the recorder stops at it and
  checks a file's length before uploading, so a too-long file doesn't use up the quota.
- Refresh buttons on the quiz and feedback results.
- `python -m sonora.cli seed-feedback --link <share link> --count N`: simulated anonymous
  listeners (feedback and first quiz attempts, through the same services as real ones) to
  test the results with many responses; refuses to run in production without `--force`.
- **Lecture analysis** (owner only): content, rhetoric and structure scored 1–10 with an
  assessment and a tip each (median of three model judgements), the time spent per topic
  and the speaking pace. Runs as its own background job after a session is ready; sessions
  from before can request it. `GET/POST /sessions/{id}/analysis`; Analysis tab with a radar
  chart.
- **Listener feedback**: the existing feedback form is now defined on the server
  (`sonora/feedback.py`), validated there and stored anonymously, once per listener.
  `POST /public/shares/{token}/feedback`; owner results with answer shares, averages and
  comments (`GET /sessions/{id}/feedback`, `…/feedback/comments`, `DELETE …/feedback/{id}`);
  Feedback tab.
- **Quiz statistics**: each listener's first quiz attempt is stored anonymously;
  `GET /sessions/{id}/quiz/results` shows per question how often each option was chosen.
  The owner's Quiz tab opens on these results ("Try it yourself" is never counted).
- **Simulated payments**: `POST /billing/checkout`, `POST /billing/cancel`,
  `GET /billing/payments`, behind a `PaymentProvider` protocol with a mock provider
  (Stripe-style test tokens). Plan & payment history in the profile.
- `GET /meta` returns the plans on sale (prices, limits) and the billing provider.
- Anonymous participant cookie (`__Host-sonora_participant`) on share links that collect
  input; only a per-session SHA-256 pseudonym is stored.
- Database migration `0002` (`payments`, `quiz_attempts`, `feedback_responses`,
  `session_analyses`).
- Frontend coverage reporting with enforced thresholds (`npm run test:coverage`, in CI).
- [docs/LLM.md](docs/LLM.md): model, prompts and the measurements behind the LLM settings.
- CI starts the production stack (database, API, nginx; no model services) and checks that
  the app, the API and the security headers are served; the job previously only validated
  the compose files.
- `tests/unit/test_deployment_files.py`: the compose files and both `.env` templates may only
  use existing settings and must list all of them with their true defaults; Docker may differ
  from the code defaults only where intended; the shipped Docker configuration must pass
  the production checks.

### Changed

- **Default LLM is Qwen3.5-9B** (`qwen3.5:9b`), with its recommended sampling
  (`SONORA_LLM_TEMPERATURE` 0.7, new `_TOP_P` 0.8, `_TOP_K` 20, `_PRESENCE_PENALTY` 1.5) and
  16K context (32K in Docker). Every call states `think` explicitly (Qwen3.5 reasons by
  default; measured, reasoning didn't improve results at 7–9x the cost). Score and topic
  calls use no presence penalty; every call has an output cap.
- Prompts: all tasks on a lecture share one prefix (transcript first, task last), so Ollama
  reuses its cache of the transcript (4.5 s → 0.2–0.8 s per further task); the quiz prompt
  asks for understanding instead of trivia; the score prompt states whether the speaking
  pace is below, within or above the typical range instead of leaving that comparison to
  the model; the chat declines requests unrelated to the lecture's subject (measured in
  `docs/LLM.md`).
- On phones, the chat's suggested questions scroll sideways in one row instead of taking
  the conversation's space.
- **New accounts start without a plan** (`SONORA_DEFAULT_PLAN=none`) and can't upload until
  they buy one; uploads then fail with `403 plan_required`.
- Public rate limits sized for lecture halls behind one IP: 600 share reads/min, 300 quiz
  checks/min per IP, plus per-listener limits.
- Share dialog selects the feedback form by default.
- **The UI is English throughout**: the profile, plan & billing, the share dialog and the
  participant page were German. Dates use the English format, prices read "€49".
- **Docker configuration**: any backend setting can now be set in `.env` under its `SONORA_`
  name (Compose passes the file to `api`, `worker` and `migrate`); settings that
  `docker-compose.yml` maps or pins (security-relevant ones) take precedence. Values shared by
  several services (LLM model, context length, upload limit, Ollama image) are defined once.
  Both `.env.example` files now list every setting (the Docker one all that the stack leaves
  open, naming the ones it fixes), commented out with their defaults; the Docker one also
  documents `TRUSTED_PROXY_CIDR` and `WITH_CUDA`. docs/DEPLOYMENT.md explains where each
  setting comes from and which code defaults Docker overrides. The Docker template warns
  against open registration while payments are simulated and against `@`, `%`, `$` in the
  database password (it becomes part of the database URL).
- The frontend no longer has its own price list: plans and prices are shown only as `/meta`
  reports them ("Loading plans…" until then). The landing page centres the plans on sale.
- **Landing page** features listener feedback, quiz results and the lecture analysis, with
  previews built from the app's own charts. Claims of features that don't exist were removed:
  the recap video, automatic speaker separation, editable scripts, verbatim quotes,
  "client-ready reports", "custom branding" and "priority rendering".
- **Lecture analysis layout**: the radar chart and a summary (speaking pace, topics and the
  tips for next time) now sit side by side at equal height, with the three assessments as
  equal cards below, instead of a chart column with empty space under it. The "Generated by"
  line under the analysis is gone; the subtitle says it is assessed by AI.
- The share page and the feedback form tell the trainer to use a private window or another
  browser to try them as a listener.
- Session processing failures now say "Processing failed" (the word "analysis" now means
  the lecture analysis).

### Removed

- `plan` in `POST /auth/register` (ignored if sent).
- `SONORA_LLM_THINK` (ignored if still set).

### Security

- A production build of the frontend embedded the demo login (button and password) whenever a
  `VITE_DEMO_*` variable was set for it, e.g. by a local `Frontend/.env`, which also went into
  the web image. The demo login now exists only in development builds, and the image build
  excludes env files.
- Production now refuses to start with `SONORA_RATE_LIMIT_ENABLED=false` (it silently lifted
  the per-account sign-in lockout as well) or `SONORA_DATABASE_ECHO=true` (it logs SQL
  parameters: emails, password hashes, transcripts).
- Fixed: any client could sign up with a paid plan (`"plan": "pro"`) without paying, and
  cancelling the checkout still left the paid plan active.
- Card details never reach the server; the simulated checkout accepts only test cards and
  disables browser autofill.
- The QR code is rendered as React SVG elements instead of injected markup.
- `docker-compose.dev.yml` publishes the API on `127.0.0.1` only (it trusts
  `X-Forwarded-For`, so a public port allowed spoofing client IPs past rate limits).
- Owner endpoints of the new features return `404` to other users; the analysis can't be
  shared; feedback can't be submitted cross-site or by the owner.
- The public chat requires the participant cookie, accepts only `user`/`assistant` turns of
  limited length as history and is capped per listener, IP and lecture and in concurrent
  answers. The share dialog tells the owner that the chatbot answers from the transcript even
  when the transcript isn't shared.

### Fixed

- "Show more" in the feedback comments repeated comments when listeners answered while the
  trainer was paging; the offset now counts every row received, and repeats are skipped.
- **The Docker stack served nothing**: the `web` container mounts a tmpfs over
  `/etc/nginx/conf.d`, which current Docker versions create root-owned, so the unprivileged
  nginx (uid 101) couldn't render its configuration and started without a server block
  (connection refused on the web port, container unhealthy). The tmpfs is now owned by
  uid 101. Found by running the stack (Docker Engine 29.8).
- The post-upload quota re-check now reloads the plan under the row lock.
- Every LLM request sent `keep_alive: 10m`, overriding `OLLAMA_KEEP_ALIVE=24h` of the Docker
  stack, so the model was unloaded after 10 idle minutes. `SONORA_LLM_KEEP_ALIVE` is now
  unset by default (the server's setting applies) and validated at startup.
- The "Copied!" / "Saved" indicators' timers are cleared when a component unmounts.
- A Whisper unit test assumed the test machine has no GPU.
