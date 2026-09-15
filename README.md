# Sonora — TranscriptionTool

**"From what was said."**  
Sonora wandelt Audio-Aufnahmen von Trainings- und Coaching-Sessions automatisch in Zusammenfassungen, interaktive Quizze, Recap-Videos und Transkripte um — und macht sie für Teilnehmer ohne Account zugänglich.

---

## Projektstruktur

```
TranscriptionTool/
├── Frontend/      # React + Vite — Trainer-App & Teilnehmer-Ansicht
└── README.md
```

Das Backend ist noch nicht implementiert. Alle Daten sind aktuell Mocks im Frontend.

---

## Produkt-Übersicht

Sonora richtet sich an Trainer, Coaches und Dozenten. Der Ablauf:

1. **Trainer nimmt eine Session auf** — direkt im Browser via Mikrofon
2. **Sonora analysiert die Aufnahme** — Transkription via Web Speech API, anschließend client-seitige NLP-Analyse
3. **Drei Deliverables entstehen automatisch:**
   - Script mit Key Takeaways (inkl. Zeitstempel)
   - Interaktives Multiple-Choice-Quiz, verankert in konkreten Session-Momenten
   - Vollständiges Transkript mit Sprecher-Trennung
   - *(Beta)* 90-Sekunden-Recap-Video
4. **Trainer teilt Inhalte mit Teilnehmern** — per Link, ohne dass Teilnehmer einen Account brauchen

---

## Zielgruppen

- **Trainer & Coaches** — nutzen die Trainer-App (Login erforderlich)
- **Teilnehmer** — rufen geteilte Inhalte über einen Share-Link auf (kein Account nötig)

---

## Aktueller Stand

| Bereich | Status |
|---|---|
| Frontend (Trainer-App) | ✅ Funktionsfähig mit Mock-Daten |
| Frontend (Teilnehmer-Ansicht) | ✅ Funktionsfähig mit Mock-Daten |
| Landing Page | ✅ Fertig |
| Authentifizierung | 🟡 Mock (hardcoded Demo-Account) |
| Audio-Transkription | ✅ Browser-nativ (Web Speech API) |
| NLP-Analyse | 🟡 Client-seitig (Heuristiken), kein LLM |
| Backend / API | ❌ Noch nicht implementiert |
| Datenbank / Persistenz | ❌ Noch nicht implementiert |
| Video-Generierung | 🟡 Mock-Player, keine echte Generierung |

---

## Schnellstart

```bash
cd Frontend
npm install
npm run dev
```

Dev-Server läuft auf `http://localhost:5173`.  
Demo-Login: `marie.trainer@example.com` / `demo1234`

Teilnehmer-Ansicht testen:
```
http://localhost:5173/?session=s1&tabs=script,quiz
```

Weitere Details → [`Frontend/README.md`](./Frontend/README.md)
