# Sonora — Frontend

React + Vite single-page app for trainers (record, review, share, see feedback, quiz
results and the lecture analysis) and listeners (shared links: script, quiz, transcript,
feedback). All data comes from the backend API (`/api/v1`); there is no mock data anymore.

## Tech stack

| Layer | Technology |
|---|---|
| UI framework | React 19 |
| Build tool | Vite 8 |
| Styling | Custom CSS with CSS variables (no framework) |
| Routing | State-based views + `/share/<token>` for participants (no router library) |
| Recording | `MediaRecorder` (WebM/Opus, Ogg or MP4 depending on the browser) |
| Transcription & analysis | Backend (faster-whisper + LLM) |
| Charts | Plain SVG/CSS (radar chart, bars), colours validated for the dark theme |
| Tests | Vitest + Testing Library (jsdom), V8 coverage with enforced thresholds |
| Linting | Oxlint |

## Setup

```bash
npm install
npm run dev        # http://localhost:5173 — /api is proxied to the backend (127.0.0.1:8000)
npm test           # unit + component tests
npm run test:coverage   # the same with coverage (fails below the thresholds in vite.config.js)
npm run lint
npm run build      # production bundle in dist/
```

Node 20+ (CI and Docker use Node 22). Start the backend first — see
[`../Backend/README.md`](../Backend/README.md).

## Structure

```
src/
├── App.jsx                  # boot (session restore), views, app shell, sidebar, polling
├── api.js                   # API client: cookies, CSRF header, errors, upload with progress
├── format.js                # timestamps, durations, dates, percentages, safe **bold** parsing
├── hooks.js                 # useTransient: self-resetting "Copied!" state
├── plans.js                 # plan copy; prices and limits come from /meta
├── mockPaymentProvider.js   # simulated provider SDK: test cards -> one-time tokens
├── features.js              # build-time feature switches (video mock, dev demo login)
├── Icon.jsx                 # inline SVG icon set
├── App.css / index.css      # styles and design tokens
├── components/
│   ├── Landing.jsx          # marketing page
│   ├── Login.jsx            # sign in / registration (plan picker -> checkout)
│   ├── PlanCards.jsx        # the plans on sale
│   ├── MockPayment.jsx      # simulated checkout dialog
│   ├── Recorder.jsx         # microphone recording + file upload (with progress)
│   ├── Processing.jsx       # live server-side status, retry on failure
│   ├── Results.jsx          # owner tabs: Script / Quiz / Chat / Transcript / Feedback / Analysis, share dialog, listener chat
│   ├── QuizResults.jsx      # how listeners answered (first attempts)
│   ├── FeedbackResults.jsx  # feedback shares per answer + open comments
│   ├── AnalysisView.jsx     # radar chart of the scores, time per topic
│   ├── charts.jsx           # RadarChart and BarRow (SVG/CSS, no chart library)
│   ├── QrCode.jsx           # QR code as React SVG elements
│   ├── ParticipantView.jsx  # public page for share links (the tabs the owner shared)
│   ├── FeedbackView.jsx     # the listener feedback form (questions from the server)
│   ├── Profile.jsx          # overview, settings, password, account deletion, plan & payments
│   └── ConfirmDialog.jsx    # confirmation for destructive actions
└── test/                    # Vitest suites
```

## How it talks to the backend

- **Same origin only.** In development Vite proxies `/api` to the backend; in production nginx
  does (see `nginx/`). No CORS is configured anywhere.
- **Session**: an `HttpOnly` cookie set by the backend — JavaScript can't read it, so an XSS bug
  could not steal it. After a reload the app calls `GET /auth/me` to restore the session.
- **CSRF**: the token returned by login/`/auth/me` is kept in memory (never in `localStorage`)
  and sent as `X-CSRF-Token` on every `POST`/`PATCH`/`DELETE`.
- **Session expiry**: any `401` on an authenticated call returns the user to the sign-in page.
- **Uploads** use `XMLHttpRequest` (fetch can't report upload progress) and send the audio as
  the raw request body. If an upload fails, the recording stays in memory and can be retried
  or saved locally — a lecture is never lost to a network hiccup.
- **Processing**: the app polls `GET /sessions` every 3 s while any session is being processed.
- **Quiz**: answers are graded by the server; correct options are not part of the quiz payload.
  The owner's Quiz tab opens on the listener results; "Try it yourself" is never counted.
- **Model output** (chat answers, summaries, analysis) and listener comments are rendered as
  React text. `**bold**` is parsed into `<strong>` elements; nothing uses
  `dangerouslySetInnerHTML` (the QR code is built from the QR matrix as SVG elements).
- **Plans and payments**: registration never sends a plan. The checkout dialog acts like a
  payment provider's card form: it accepts only the test cards, turns them into a one-time
  token and sends only `{plan, payment_token}`; prices shown come from `/meta`.
- **Listener feedback**: the share page renders the form the server sends and submits option
  indexes; the anonymous participant cookie is set and read by the server (`HttpOnly`).
- **Listener chat**: the server never stores a listener's conversation. The share page keeps
  it in memory and sends its last six turns with each question. It stays mounted while other
  tabs are open, so switching tabs doesn't lose it; reloading the page starts a new one.

## Views

| View | Description |
|---|---|
| `landing` | Marketing page; entry point for visitors without a session |
| `login` | Sign in or register (`meta.registration_enabled` hides registration) |
| `app` | Sidebar with sessions + recorder / processing / results; without a plan, a "Choose a plan" card |
| `profile` | Stats, activity, settings, password change, account deletion, plan & usage, payment history |
| `/share/<token>` | Participant page — only the tabs the trainer shared, no account needed; the owner sees a note that their input isn't counted |

## Environment variables

Vite reads `.env`, `.env.development` (dev server only) and `.env.production` (builds).

| Variable | Used by | Purpose |
|---|---|---|
| `API_PROXY_TARGET` | dev server | Backend URL for the `/api` proxy (default `http://127.0.0.1:8000`) |
| `VITE_DEMO_EMAIL`, `VITE_DEMO_PASSWORD` | dev only | Shows the "Use demo account" button (see `.env.development`); production builds ignore them, and the web image excludes local env files |
| `VITE_FEATURE_VIDEO` | app | `true` shows the recap-video tab (design mock; no backend support yet) |

## Production image

`Dockerfile` builds the bundle and serves it with an unprivileged nginx that

- falls back to `index.html` for SPA routes such as `/share/<token>`,
- proxies `/api` to the backend with streaming uploads and overwritten `X-Forwarded-For`,
- sends a strict Content-Security-Policy and other security headers,
- caches fingerprinted assets forever and revalidates `index.html`,
- redacts share tokens from its access log.

Runtime settings (`API_UPSTREAM`, `MAX_UPLOAD_MB`, `TRUSTED_PROXY_CIDR`) are applied from
environment variables when the container starts. See [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).
