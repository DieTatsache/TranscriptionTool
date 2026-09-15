# Sonora — TranscriptionTool

**"From what was said."**
Sonora turns audio recordings of training and coaching sessions into summaries, interactive quizzes, recap videos, and transcripts — shareable with participants via link, no account required.

---

## Project Structure

```
TranscriptionTool/
├── Frontend/      # React + Vite — trainer app & participant view
└── README.md
```

The backend is not yet implemented. All data is currently mocked in the frontend.

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
| NLP analysis | Client-side heuristics (`Frontend/src/analyze.js`) |
| Linting | Oxlint |

---

## Quick Start

```bash
cd Frontend
npm install
npm run dev
```

Dev server runs at `http://localhost:5173`.
Demo login: `marie.trainer@example.com` / `demo1234`

Test the participant view:
```
http://localhost:5173/?session=s1&tabs=script,quiz
```

Full details → [`Frontend/README.md`](./Frontend/README.md)
