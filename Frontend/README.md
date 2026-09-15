# Sonora — Frontend

React + Vite frontend for the Sonora trainer app and participant view.

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI framework | React 19 |
| Build tool | Vite 8 |
| Styling | Custom CSS with CSS variables (no framework) |
| Routing | State-based + URL parameters (no router library) |
| State management | React `useState` (no external library) |
| Audio transcription | Web Speech API (browser-native, Chrome recommended) |
| NLP analysis | Client-side heuristics in `analyze.js` |
| Linting | Oxlint |

---

## Architecture

This repository contains **the frontend only**. There is no backend — all data is mocked in `src/data.js`. Browser APIs (Web Speech API + MediaRecorder) are used directly.

```
src/
├── App.jsx                  # View router (state-based, no React Router)
├── App.css                  # All styles
├── index.css                # CSS variables, reset, animations
├── data.js                  # Mock data (sessions, quizzes, transcripts)
├── analyze.js               # Client-side NLP analysis of transcript entries
├── Icon.jsx                 # Inline SVG icon set (no external dependency)
└── components/
    ├── Landing.jsx          # Marketing landing page
    ├── Login.jsx            # Login screen (mock auth)
    ├── Profile.jsx          # Profile page (overview, settings, billing)
    ├── Recorder.jsx         # Recording screen with Web Speech API + waveform
    ├── Processing.jsx       # Loading screen during analysis
    ├── Results.jsx          # Trainer results view (Script/Quiz/Video/Chat/Transcript)
    └── ParticipantView.jsx  # Public participant view (no login required)
```

### Navigation / Views

The app has no router — the active view is controlled via state:

| View | Description |
|---|---|
| `landing` | Marketing page (entry point) |
| `login` | Login screen (mock: `marie.trainer@example.com` / `demo1234`) |
| `app` | Main trainer app (sidebar + sessions) |
| `profile` | Profile page |
| Participant URL | Detected from `?session=` on page load — bypasses auth entirely |

### Share Links (Participant View)

Format: `/?session=<sessionId>&tabs=<tab1>,<tab2>,...`

Available tab values: `script`, `quiz`, `video`, `transcript`

Examples:
```
/?session=s1&tabs=script,quiz
/?session=s2&tabs=script,quiz,video,transcript
/?session=s3&tabs=quiz
```

Session IDs `s1`–`s4` are the demo sessions. New sessions get a dynamic ID (`session-<timestamp>`) that would be persisted via the backend in the real product.

---

## Setup

```bash
npm install
npm run dev       # Dev server at http://localhost:5173
npm run build     # Production build
npm run lint      # Oxlint
```

Node 18+ recommended.
