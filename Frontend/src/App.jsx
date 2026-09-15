import { useState } from "react";
import "./App.css";
import Icon from "./Icon.jsx";
import { DEMO_SESSIONS } from "./data.js";
import { analyzeTranscript } from "./analyze.js";
import Landing from "./components/Landing.jsx";
import Recorder from "./components/Recorder.jsx";
import Processing from "./components/Processing.jsx";
import Results from "./components/Results.jsx";

export default function App() {
  const [view, setView] = useState("landing");

  if (view === "landing") {
    return <Landing onEnter={() => setView("app")} />;
  }
  return <AppShell onHome={() => setView("landing")} />;
}

function AppShell({ onHome }) {
  const [stage, setStage] = useState("results");
  const [sessions, setSessions] = useState(DEMO_SESSIONS);
  const [activeSession, setActiveSession] = useState(DEMO_SESSIONS[0].id);
  // Extra content for user-recorded sessions: { [id]: content }
  const [liveContent, setLiveContent] = useState({});
  const [pendingAnalysis, setPendingAnalysis] = useState(null); // { seconds, entries }

  const stopRecording = (seconds, entries) => {
    setPendingAnalysis({ seconds, entries });
    setStage("processing");
  };

  const finishProcessing = () => {
    const { seconds, entries } = pendingAnalysis ?? { seconds: 0, entries: [] };
    const analyzed = analyzeTranscript(entries, seconds);
    const id = "session-" + Date.now();

    const meta = analyzed?.sessionMeta ?? {
      title: "New Session — " + new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
      date: new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
      duration: seconds > 0 ? formatDuration(seconds) : "< 1s",
      quizzes: 0,
    };

    setSessions((prev) => [{ id, ...meta }, ...prev]);

    if (analyzed?.content) {
      setLiveContent((prev) => ({ ...prev, [id]: analyzed.content }));
    }

    setActiveSession(id);
    setPendingAnalysis(null);
    setStage("results");
  };

  const deleteSession = (id) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (activeSession === id && next.length > 0) {
        setActiveSession(next[0].id);
      }
      return next;
    });
    setLiveContent((prev) => { const n = { ...prev }; delete n[id]; return n; });
  };

  const reset = () => setStage("results");

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        active={activeSession}
        onSelect={(id) => { setActiveSession(id); setStage("results"); }}
        onNew={() => setStage("recording")}
        onDelete={deleteSession}
        onHome={onHome}
        usedCount={sessions.length}
      />

      <main className="main">
        <TopBar
          stage={stage}
          session={sessions.find((s) => s.id === activeSession)}
          onNew={() => setStage("recording")}
        />

        <div className="stage">
          {stage === "recording" && <Recorder onStop={stopRecording} onCancel={reset} />}
          {stage === "processing" && <Processing onDone={finishProcessing} hasRealContent={!!pendingAnalysis?.entries?.length} />}
          {stage === "results" && <Results sessionId={activeSession} liveContent={liveContent} />}
        </div>
      </main>
    </div>
  );
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  if (s === 0) return `${m} min`;
  return `${m}m ${s}s`;
}

function Sidebar({ sessions, active, onSelect, onNew, onDelete, onHome, usedCount }) {
  return (
    <aside className="sidebar">
      <button className="brand brand-btn" onClick={onHome} title="Back to home">
        <div className="brand-mark">
          <Icon name="wave" size={20} />
        </div>
        <div className="brand-text">
          <strong>Sonora</strong>
          <span>from what was said</span>
        </div>
      </button>

      <button className="btn btn-primary btn-block" onClick={onNew}>
        <Icon name="mic" size={16} /> New session
      </button>

      <div className="side-label">Your sessions</div>
      <nav className="session-list">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={"session-item" + (s.id === active ? " active" : "")}
          >
            <button
              className="session-item-btn"
              onClick={() => onSelect(s.id)}
            >
              <span className="session-title">{s.title}</span>
              <span className="session-meta">
                {s.date} · {s.duration} · {s.quizzes} quiz Qs
              </span>
            </button>
            <button
              className="session-delete"
              title="Delete session"
              onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
            >
              <Icon name="close" size={13} />
            </button>
          </div>
        ))}
      </nav>

      <div className="side-footer">
        <div className="plan-card">
          <div className="plan-top">
            <span className="plan-name">Trainer Plan</span>
            <span className="plan-badge">Active</span>
          </div>
          <div className="plan-bar">
            <div className="plan-bar-fill" style={{ width: `${Math.min(100, (usedCount / 10) * 100)}%` }} />
          </div>
          <span className="plan-note">{usedCount} of 10 sessions this month</span>
        </div>
      </div>
    </aside>
  );
}

function TopBar({ stage, session, onNew }) {
  const recordingLabel = "Recording session";
  const processingLabel = "Analyzing what was said";
  const title = stage === "recording" ? recordingLabel
    : stage === "processing" ? processingLabel
    : (session?.title ?? "Session");
  const sub = stage === "results" && session
    ? `${session.date} · ${session.duration} · generated from audio transcript`
    : null;

  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1>{title}</h1>
        {sub && <span className="topbar-sub">{sub}</span>}
      </div>
      <div className="topbar-actions">
        <button className="btn btn-ghost" onClick={onNew}>
          <Icon name="plus" size={16} /> New
        </button>
        <div className="avatar">MT</div>
      </div>
    </header>
  );
}
