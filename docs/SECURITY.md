# Security

This document describes how Sonora protects accounts, recordings and generated content, what is
deliberately out of scope for now, and what to check before going live.

## What we protect

| Asset | Why it matters |
|---|---|
| Recordings and transcripts | Lectures and coaching sessions can contain personal, confidential or health-related speech |
| Accounts | Access to all of a trainer's sessions, share links and chat |
| Share links | Anyone holding one can read the shared parts of a session |
| Listener input | Anonymous feedback and quiz answers; must stay anonymous and hard to fake in bulk |
| Lecture analysis | A personal assessment of the lecturer; only they may see it |
| Plans | Paid features; must not be obtainable by editing a request |
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
| Answer leakage | Quizzes are delivered without the answer key and graded on the server; only the owner's statistics show the correct options |
| Getting a paid plan without paying | The client can't choose a plan at sign-up (new accounts get `none`, a regression test sends `"plan": "pro"`); only a successful checkout grants a plan; prices come from the server's catalog, never from the request |
| Card data exposure | Card details never reach the server: the browser-side provider form turns them into a one-time token (`tok_…`), the API only accepts such tokens (`^[A-Za-z0-9_-]+$`); only brand and last four digits reported by the provider are stored. The simulated form refuses everything but documented test cards and disables autofill, so no real card is typed into it |
| Card testing, double charges | Checkout limited to 10 attempts per hour per user; declined attempts are recorded; the user row is locked during a checkout (PostgreSQL) and buying the current plan again is refused |
| Fake or repeated feedback / quiz statistics | One response and one counted quiz attempt per listener and session (unique constraint on a per-session pseudonym of a random `HttpOnly`, `SameSite=Strict`, `__Host-` cookie); a missing or malformed cookie is refused for feedback and not counted for the quiz; limits per IP (600 feedback/h, 300 quiz checks/min) and per listener (10/h, 30/min); at most 5,000 stored responses and attempts per session; the owner can delete individual responses |
| Owner skewing their own results | The signed-in owner is recognised on public pages: their feedback is refused (`own_session`) and their quiz attempts are not counted |
| Cross-site submission of feedback | `SameSite=Strict` participant cookie (a foreign page can't send it) plus the `Origin` check on every state-changing request |
| Listener chat as a free LLM, GPU exhaustion | Only on links that share the chat, only with the participant cookie; limits per listener (5/min, 60/day), per IP (300/h) and per lecture (600/h, all listeners together); each API process generates at most 4 listener answers at once, so further questions get `503 assistant_busy` instead of queueing for the GPU; answers capped at 600 tokens. The prompt declines requests unrelated to the lecture (10 of 12 in the measurement, see [LLM.md](LLM.md)). That saves GPU time, but the limits are the actual boundary |
| Forged chat history | Listener conversations aren't stored; the page sends at most 6 earlier turns (2,000 characters each, roles `user`/`assistant` only, so no system instructions), after the server's rules and the fenced transcript. A forged turn can only change the answer that listener sees |
| Exposure of the lecture analysis | Owner-only endpoints (`404` for everyone else); the share-tab enum has no analysis entry, so no link can expose it (tested) |
| Listener tracking | No account, no IP or user agent stored with responses; the stored key is `SHA-256(session id + cookie)`, so one browser's answers can't be linked across sessions; listeners' chat questions aren't stored at all; the cookie is only set on links with the quiz, feedback form or chat, and never for the owner |
| Malicious uploads | Authenticated before any byte is read; streaming size limit; format detected from magic bytes (the client's `Content-Type` is ignored); random server-side file names; keys validated against path traversal; duration probed before decoding; parsing happens in the isolated worker |
| Resource exhaustion | Body size limits (64 KB JSON, 200 MB uploads); rate limits on uploads (10/h), the owner's chat (10/min, 300/day, also on their own share link), the listener chat (see above), password checks (5/15 min), analysis requests (10/h), checkouts (10/h) and public links (600 reads/min per IP: a lecture hall's listeners often share one address); monthly plan quotas; bounded LLM concurrency, output caps and timeouts; max audio length |
| XSS | React escapes all output; model output and listener comments are rendered as text (bold via React elements, never raw HTML); the QR code is drawn as React SVG elements (no `dangerouslySetInnerHTML` anywhere); strict CSP (`script-src 'self'`, no inline scripts or styles, `frame-ancestors 'none'`) |
| Prompt injection via transcripts | Transcripts are fenced as data in every prompt; the model has no tools or actions; output is constrained to a JSON schema and validated (scores must be integers 1–10, timestamps must match real segments); the analysis is available to the owner only, the chat to listeners only on links that share it; what a listener makes the model say is shown only to them |
| Clickjacking, MIME sniffing, referrer leaks | `X-Frame-Options: DENY` / `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer` (share URLs never leak) |
| Host header attacks | Host allow-list (`SONORA_ALLOWED_HOSTS`, required in production) |
| Information disclosure | Generic `500` bodies; validation errors never echo submitted values; API docs disabled in production; `server_tokens off` |
| Spoofed client IPs (rate-limit bypass) | nginx overwrites `X-Forwarded-For`; only a configured TLS proxy (`TRUSTED_PROXY_CIDR`) may set the client IP; the API is reachable only from nginx (the debug override `docker-compose.dev.yml` publishes it on `127.0.0.1` only) |
| Misconfiguration | With `SONORA_ENVIRONMENT=production`, startup fails on insecure cookies, a `*` host allow-list, missing origins, SQLite, the fake transcriber, disabled rate limits (they also enforce the sign-in lockout) or SQL echo (it would log personal data). In Docker, `docker-compose.yml` pins the security-relevant settings (production mode, `Secure` cookies, PostgreSQL, shared rate limits, separate worker); `SONORA_` lines in `.env` can't override them. `tests/unit/test_deployment_files.py` checks that the shipped compose file and template pass the production checks |
| Container escape / lateral movement | Non-root users, read-only root file systems, all capabilities dropped, `no-new-privileges`; database and Valkey on an internal network without internet access; only nginx is published |

## Implementation reference

| Area | Where |
|---|---|
| Password hashing and policy, tokens | `Backend/sonora/security.py` |
| Sign-in, sessions, lockout | `Backend/sonora/services/auth.py`, `Backend/sonora/api/deps.py` |
| CSRF, origin check, headers, body limits | `Backend/sonora/api/deps.py`, `Backend/sonora/api/middleware.py` |
| Upload validation and storage | `Backend/sonora/storage.py`, `Backend/sonora/api/routes/sessions.py` |
| Share links | `Backend/sonora/services/shares.py`, `Backend/sonora/api/routes/public.py` |
| Listener identity, feedback, quiz attempts | `Backend/sonora/api/deps.py` (participant cookie), `Backend/sonora/security.py` (`participant_key`), `Backend/sonora/services/feedback.py`, `Backend/sonora/services/quiz.py` |
| Listener chat (limits, busy cap, no storage) | `Backend/sonora/api/routes/public.py`, `Backend/sonora/services/chat.py`, `Backend/sonora/ai/prompts.py` (scope rule) |
| Plans and payments | `Backend/sonora/plans.py`, `Backend/sonora/billing.py`, `Backend/sonora/services/billing.py`, `Frontend/src/mockPaymentProvider.js` |
| Lecture analysis access | `Backend/sonora/api/routes/analysis.py`, `Backend/sonora/services/analysis.py` |
| Rate limits | `Backend/sonora/ratelimit.py` + the services |
| Production config checks | `Backend/sonora/config.py` |
| Frontend CSRF/session handling | `Frontend/src/api.js` |
| Web server headers, CSP, log redaction | `Frontend/nginx/` |
| Container hardening, networks | `docker-compose.yml` |

The HTTP-level controls are covered by tests: `tests/api/test_auth.py`,
`tests/api/test_http_security.py`, `tests/api/test_sessions.py`, `tests/api/test_shares.py`,
`tests/api/test_races_and_cleanup.py`, `tests/api/test_billing.py`,
`tests/api/test_feedback.py`, `tests/api/test_quiz_results.py`, `tests/api/test_analysis.py`,
`tests/api/test_public_chat.py`,
`Frontend/src/test/api.test.js` and `Frontend/src/test/payment.test.jsx`.

## Privacy

- **Nothing leaves your infrastructure.** Transcription and text generation run on your own
  servers. The only outbound connections are model downloads (Ollama registry, Hugging Face).
- **Data minimisation.** Audio is deleted as soon as it is transcribed (`SONORA_KEEP_AUDIO`
  turns this off). IP address and user agent are stored only with an active sign-in and are
  purged when it expires.
- **Right to erasure.** Deleting a session removes its transcript, content, chat, share links
  and audio. Deleting the account (Profile → Settings) removes everything the user owns.
- **Logs** contain request metadata, never passwords, tokens, transcripts, chat content or
  feedback. Share tokens are redacted from API and nginx access logs.
- **Listeners** stay anonymous: a feedback response is its ratings, an optional comment and a
  timestamp; a quiz attempt is the chosen options and the score. Both carry only a
  per-session pseudonym of a random cookie (see above). They are deleted with the session or
  the account, and the owner can delete single responses (e.g. on a listener's request).
  Questions to the chat aren't stored: the page keeps the conversation and sends it along
  with each question, and the trainer can't see it.
  The participant cookie is functional (it prevents duplicate answers and limits the chat per
  listener) and is set only on links with the quiz, feedback form or chat; mention it in your
  privacy notice.
- **Payments** store plan, amount, status, card brand and last four digits — never card
  numbers, expiry dates or CVCs.

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
8. **Payments are simulated in every environment** (a deliberate product decision until a
   payment provider is chosen): the checkout accepts test cards, so anyone can activate
   Trainer or Pro without paying. A real provider needs, at least: its hosted card fields
   (keeps the server out of PCI DSS scope), server-side webhooks as the source of truth,
   idempotency keys, renewals and failed-payment handling, and invoices — whose statutory
   retention (e.g. 10 years in Germany) conflicts with "delete everything" on account
   deletion and must be handled separately.
9. **Anonymous input can be repeated** by clearing cookies or using several browsers; the
   limits above make bulk manipulation slow but not impossible. If results must be
   tamper-proof, require sign-in or one-time codes for listeners.
10. **AI assessments can be wrong.** The lecture analysis is a model's opinion, shown only to
    the lecturer and labelled as such; it must not be used to evaluate employees or
    lecturers without human review (in the EU this would likely be a high-risk use under the
    AI Act).

## Production checklist

- [ ] Served **only over HTTPS** (e.g. `docker-compose.tls.yml`), with `HSTS_ENABLED=true`.
- [ ] `PUBLIC_HOST` / `PUBLIC_ORIGIN` set to the real address; nothing else in the host allow-list.
- [ ] Strong, unique `POSTGRES_PASSWORD`; `.env` readable only by the deploying user (`chmod 600 .env`).
- [ ] Only ports 80/443 (or the web port behind your own proxy) reachable from outside.
- [ ] `TRUSTED_PROXY_CIDR` set to the exact address of your TLS proxy, if you use your own.
- [ ] Decide on `REGISTRATION_ENABLED` — keep it closed while payments are simulated (anyone
      could otherwise "buy" Pro with a test card and fill the processing queue) and create
      accounts with `create-user`.
- [ ] `SONORA_PASSWORD_MIN_LENGTH=15`: NIST SP 800-63B-4's minimum for passwords that are the
      only sign-in factor (the code default of 12 suits development).
- [ ] No demo account in production (`seed-demo` refuses to run there; never set
      `VITE_DEMO_*` for production builds).
- [ ] Database backups configured and restore tested (see DEPLOYMENT.md).
- [ ] Images pinned and updated regularly (`OLLAMA_IMAGE`, base images); dependency audit run.
- [ ] Logs collected centrally and monitored for `failed sign-in` bursts and 5xx errors.
- [ ] Privacy policy and data processing agreements cover recordings of third parties
      (participants must know they are being recorded), the anonymous feedback and the
      participant cookie.
- [ ] Users know that payments are simulated (or a real payment provider is connected, see
      *Known limitations*).

## Reporting a vulnerability

Please report security issues privately to the maintainers rather than opening a public issue.
