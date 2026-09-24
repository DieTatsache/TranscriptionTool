# Security

This document describes how Sonora protects accounts, recordings and generated content, what is
deliberately out of scope for now, and what to check before going live.

## What we protect

| Asset | Why it matters |
|---|---|
| Recordings and transcripts | Lectures and coaching sessions can contain personal, confidential or health-related speech |
| Accounts | Access to all of a trainer's sessions, share links and chat |
| Share links | Anyone holding one can read the shared parts of a session |
| Compute (Whisper, LLM) | Expensive; abuse means cost and denial of service |

## Threats and controls

| Threat | Controls |
|---|---|
| Password guessing / credential stuffing | Per-IP limit (20/min) and per-email lockout (5 failures / 15 min, counted for unknown emails too); Argon2id hashing |
| Account enumeration | Identical error and similar timing for unknown email vs. wrong password (a dummy hash is verified) — *registration still reveals taken emails, see limitations* |
| Session theft (XSS, logs, database leak) | Opaque 256-bit token in an `HttpOnly` cookie; only its SHA-256 is stored; tokens never appear in URLs or logs |
| Session fixation / reuse | New token on every sign-in (the browser's previous session is revoked); logout deletes the session server-side; 14-day absolute and 72-hour idle expiry |
| Cross-site request forgery | Per-session CSRF token in `X-CSRF-Token` on all state-changing requests; `SameSite=Strict` cookie; `Origin` check; JSON bodies require `application/json` |
| Access to other users' data (IDOR) | Every query is scoped to the owner; unknown and foreign ids both return `404`; random UUIDs |
| Stolen password after a leak | Password change and email change sign out all other devices; email changes require the current password |
| Share-link guessing or widening | 256-bit tokens; the visible tabs are stored on the server (editing the URL can't reveal more); 30-day default expiry; revocable; rate limited |
| Answer leakage | Quizzes are delivered without the answer key and graded on the server |
| Malicious uploads | Authenticated before any byte is read; streaming size limit; format detected from magic bytes (the client's `Content-Type` is ignored); random server-side file names; keys validated against path traversal; duration probed before decoding; parsing happens in the isolated worker |
| Resource exhaustion | Body size limits (64 KB JSON, 200 MB uploads); rate limits on uploads (10/h), chat (10/min, 300/day), password checks (5/15 min) and public links; monthly plan quotas; bounded LLM concurrency and timeouts; max audio length |
| XSS | React escapes all output; model output is rendered as text (bold via React elements, never raw HTML); strict CSP (`script-src 'self'`, no inline scripts or styles, `frame-ancestors 'none'`) |
| Prompt injection via transcripts | Transcripts are fenced as data in every prompt; the model has no tools or actions; output is constrained to a JSON schema and validated; chat is available to the owner only |
| Clickjacking, MIME sniffing, referrer leaks | `X-Frame-Options: DENY` / `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer` (share URLs never leak) |
| Host header attacks | Host allow-list (`SONORA_ALLOWED_HOSTS`, required in production) |
| Information disclosure | Generic `500` bodies; validation errors never echo submitted values; API docs disabled in production; `server_tokens off` |
| Spoofed client IPs (rate-limit bypass) | nginx overwrites `X-Forwarded-For`; only a configured TLS proxy (`TRUSTED_PROXY_CIDR`) may set the client IP; the API is reachable only from nginx |
| Misconfiguration | With `SONORA_ENVIRONMENT=production`, startup fails on insecure cookies, a `*` host allow-list, missing origins, SQLite or the fake transcriber |
| Container escape / lateral movement | Non-root users, read-only root file systems, all capabilities dropped, `no-new-privileges`; database and Valkey on an internal network without internet access; only nginx is published |

## Implementation reference

| Area | Where |
|---|---|
| Password hashing and policy, tokens | `Backend/sonora/security.py` |
| Sign-in, sessions, lockout | `Backend/sonora/services/auth.py`, `Backend/sonora/api/deps.py` |
| CSRF, origin check, headers, body limits | `Backend/sonora/api/deps.py`, `Backend/sonora/api/middleware.py` |
| Upload validation and storage | `Backend/sonora/storage.py`, `Backend/sonora/api/routes/sessions.py` |
| Share links | `Backend/sonora/services/shares.py`, `Backend/sonora/api/routes/public.py` |
| Rate limits | `Backend/sonora/ratelimit.py` + the services |
| Production config checks | `Backend/sonora/config.py` |
| Frontend CSRF/session handling | `Frontend/src/api.js` |
| Web server headers, CSP, log redaction | `Frontend/nginx/` |
| Container hardening, networks | `docker-compose.yml` |

The HTTP-level controls are covered by tests: `tests/api/test_auth.py`,
`tests/api/test_http_security.py`, `tests/api/test_sessions.py`, `tests/api/test_shares.py`,
`tests/api/test_races_and_cleanup.py` and `Frontend/src/test/api.test.js`.

## Privacy

- **Nothing leaves your infrastructure.** Transcription and text generation run on your own
  servers. The only outbound connections are model downloads (Ollama registry, Hugging Face).
- **Data minimisation.** Audio is deleted as soon as it is transcribed (`SONORA_KEEP_AUDIO`
  turns this off). IP address and user agent are stored only with an active sign-in and are
  purged when it expires.
- **Right to erasure.** Deleting a session removes its transcript, content, chat, share links
  and audio. Deleting the account (Profile → Settings) removes everything the user owns.
- **Logs** contain request metadata, never passwords, tokens, transcripts or chat content.
  Share tokens are redacted from API and nginx access logs.

## Known limitations

These are accepted for now and should be addressed before or soon after launch:

1. **No email verification or password reset.** Anyone can register with any address, taken
   emails can be discovered via registration (rate limited), and a forgotten password needs an
   administrator. This needs email delivery infrastructure (SMTP) first.
2. **No multi-factor authentication.**
3. **No malware scanning of uploads.** Audio is parsed by FFmpeg (PyAV) in the worker
   container. Keep the worker image up to date (FFmpeg CVEs), or add a scanner if
   non-audio files could be a concern.
4. **Share tokens are stored in plain text** (by design, see ARCHITECTURE.md). Anyone with read
   access to the database can read shared content anyway.
5. **Security events go to the application log**, not to a separate tamper-evident audit store.
6. **In-memory rate limiting** in local development is per process. Production uses Valkey.
7. **Dependency scanning** is not automated yet. Run `uvx pip-audit` (Backend) and `npm audit`
   (Frontend) regularly or add them to CI.

## Production checklist

- [ ] Served **only over HTTPS** (e.g. `docker-compose.tls.yml`), with `HSTS_ENABLED=true`.
- [ ] `PUBLIC_HOST` / `PUBLIC_ORIGIN` set to the real address; nothing else in the host allow-list.
- [ ] Strong, unique `POSTGRES_PASSWORD`; `.env` readable only by the deploying user (`chmod 600 .env`).
- [ ] Only ports 80/443 (or the web port behind your own proxy) reachable from outside.
- [ ] `TRUSTED_PROXY_CIDR` set to the exact address of your TLS proxy, if you use your own.
- [ ] Decide on `REGISTRATION_ENABLED` — close it if accounts should be created by admins only.
- [ ] No demo account in production (`seed-demo` refuses to run there; never set
      `VITE_DEMO_*` for production builds).
- [ ] Database backups configured and restore tested (see DEPLOYMENT.md).
- [ ] Images pinned and updated regularly (`OLLAMA_IMAGE`, base images); dependency audit run.
- [ ] Logs collected centrally and monitored for `failed sign-in` bursts and 5xx errors.
- [ ] Privacy policy and data processing agreements cover recordings of third parties
      (participants must know they are being recorded).

## Reporting a vulnerability

Please report security issues privately to the maintainers rather than opening a public issue.
