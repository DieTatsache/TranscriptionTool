# Sonora — Frontend

**"From what was said."**  
Sonora wandelt Audio-Aufnahmen von Trainings- und Coaching-Sessions automatisch in Zusammenfassungen, interaktive Quizze, Recap-Videos und Transkripte um.

---

## Was ist Sonora?

Sonora richtet sich an Trainer, Coaches und Dozenten. Nach einer Session wird die Aufnahme analysiert und daraus werden drei Deliverables generiert:

1. **Script** — Narrativer Überblick mit Key Takeaways, jeweils mit Zeitstempel
2. **Quiz** — Automatisch generierte Multiple-Choice-Fragen, verankert in konkreten Session-Momenten
3. **Transkript** — Vollständiges Wort-für-Wort-Protokoll mit Sprecher-Trennung
4. **Video** *(Beta)* — 90-Sekunden-Recap-Clip aus den wichtigsten Momenten

Teilnehmer können die Inhalte über einen Share-Link aufrufen — ohne Account.

---

## Architektur

Dieses Repository enthält **ausschließlich das Frontend**. Es gibt aktuell kein Backend — alle Daten sind Mock-Daten in `src/data.js`. Die Browser-APIs (Web Speech API + MediaRecorder) werden direkt im Browser genutzt.

```
src/
├── App.jsx                  # Router-Logik (state-based, kein React Router)
├── App.css                  # Alle Styles
├── index.css                # CSS-Variablen, Reset, Animationen
├── data.js                  # Mock-Daten (Sessions, Quizze, Transkripte)
├── analyze.js               # Client-seitige NLP-Analyse von Transkript-Entries
├── Icon.jsx                 # Inline-SVG-Icon-Set (keine externe Abhängigkeit)
└── components/
    ├── Landing.jsx          # Marketing-Landing-Page
    ├── Login.jsx            # Anmelde-Screen (Mock-Auth)
    ├── Profile.jsx          # Profil-Seite (Übersicht, Einstellungen, Abrechnung)
    ├── Recorder.jsx         # Aufnahme-Screen mit Web Speech API + Waveform
    ├── Processing.jsx       # Lade-Screen während der Analyse
    ├── Results.jsx          # Trainer-Ergebnis-Ansicht (Script/Quiz/Video/Chat/Transkript)
    └── ParticipantView.jsx  # Öffentliche Teilnehmer-Ansicht (kein Login nötig)
```

### Navigation / Views

Die App hat keinen Router — die Ansicht wird über State gesteuert:

| View | Beschreibung |
|---|---|
| `landing` | Marketing-Seite (Startpunkt) |
| `login` | Anmelde-Screen (Mock: `marie.trainer@example.com` / `demo1234`) |
| `app` | Haupt-App für Trainer (Sidebar + Sessions) |
| `profile` | Profil-Seite |
| Participant-URL | Wird beim Seitenload aus `?session=` erkannt — bypassed Auth |

### Share-Links (Teilnehmer-Ansicht)

Format: `/?session=<sessionId>&tabs=<tab1>,<tab2>,...`

Mögliche Tab-Werte: `script`, `quiz`, `video`, `transcript`

Beispiele:
```
/?session=s1&tabs=script,quiz
/?session=s2&tabs=script,quiz,video,transcript
/?session=s3&tabs=quiz
```

Die Session-IDs `s1`–`s4` sind die Demo-Sessions. Neue Sessions erhalten eine dynamische ID (`session-<timestamp>`), die im echten Produkt über das Backend persistiert werden würde.

---

## Setup

```bash
npm install
npm run dev       # Dev-Server auf http://localhost:5173
npm run build     # Produktions-Build
npm run lint      # Oxlint
```

Node 18+ empfohlen.

---

## Mock-Daten

Alle Demo-Inhalte liegen in `src/data.js`:

- **4 Demo-Sessions** (`s1`–`s4`) mit vollständigen Transkripten, Skripten und Quizzen
- **Mock-Auth**: `marie.trainer@example.com` / `demo1234`
- **Chat-Antworten**: Keyword-basiertes Matching gegen Transkript-Inhalte

---

## Geplante Backend-Integration

Folgende Funktionen sind im Frontend als Mock vorhanden und müssen später mit dem Backend verbunden werden:

| Feature | Mock aktuell | Backend-Endpunkt (geplant) |
|---|---|---|
| Authentifizierung | Hardcoded User-Objekt | `POST /auth/login` |
| Session-Liste | `DEMO_SESSIONS` in data.js | `GET /sessions` |
| Session-Inhalte | `SESSION_CONTENT` in data.js | `GET /sessions/:id/content` |
| Audio-Analyse | Client-seitige NLP (`analyze.js`) | `POST /sessions/:id/analyze` |
| Share-Links | URL-Parameter mit Mock-Daten | Token-basierte Links via Backend |
| Chatbot | Keyword-Matching | LLM-API mit RAG über Transkript |

---

## Tech Stack

- **React 19** mit Vite 8
- **Kein externes State-Management** — React `useState` reicht
- **Kein CSS-Framework** — custom CSS mit CSS-Variablen
- **Keine Routing-Bibliothek** — state-based + URL-Parameter für Participant-Links
- **Web Speech API** — Browser-native Transkription (Chrome empfohlen)
- **Oxlint** — Linting
