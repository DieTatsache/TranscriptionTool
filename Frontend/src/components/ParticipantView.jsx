import { useState } from "react";
import Icon from "../Icon.jsx";
import { SESSION_CONTENT, DEMO_SESSIONS } from "../data.js";
import { ScriptView, QuizView, VideoView, TranscriptView } from "./Results.jsx";

const TAB_DEFS = [
  { id: "script", label: "Script", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "video", label: "Video", icon: "video" },
  { id: "transcript", label: "Transcript", icon: "transcript" },
];

export default function ParticipantView({ sessionId, tabs }) {
  const allowedTabs = tabs ? tabs.split(",") : ["script", "quiz", "video", "transcript"];
  const visibleTabs = TAB_DEFS.filter((t) => allowedTabs.includes(t.id));

  const [activeTab, setActiveTab] = useState(visibleTabs[0]?.id ?? "script");

  const content = SESSION_CONTENT[sessionId] ?? SESSION_CONTENT.s1;
  const isDemo = !SESSION_CONTENT[sessionId];
  const sessionMeta = DEMO_SESSIONS.find((s) => s.id === sessionId);
  const title = sessionMeta?.title ?? content.script?.title ?? "Session";

  return (
    <div className="participant-page">
      {/* Nav */}
      <nav className="participant-nav">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="wave" size={18} />
          </div>
          <div className="brand-text">
            <strong>Sonora</strong>
            <span>from what was said</span>
          </div>
        </div>
        <div className="participant-session-title">{title}</div>
        <a className="btn btn-ghost btn-sm participant-cta" href="/">
          Für Trainer →
        </a>
      </nav>

      {isDemo && (
        <div className="participant-demo-banner">
          <Icon name="spark" size={14} /> Demo-Session — dieser Link zeigt Beispieldaten.
        </div>
      )}

      {/* Content */}
      <div className="participant-body">
        <div className="tabs">
          {visibleTabs.map((t) => (
            <button
              key={t.id}
              className={"tab" + (activeTab === t.id ? " active" : "")}
              onClick={() => setActiveTab(t.id)}
            >
              <Icon name={t.icon} size={16} />
              {t.label}
            </button>
          ))}
        </div>

        <div className="tab-panel">
          {activeTab === "script" && <ScriptView script={content.script} />}
          {activeTab === "quiz" && <QuizView quiz={content.quiz} key={sessionId} />}
          {activeTab === "video" && <VideoView />}
          {activeTab === "transcript" && <TranscriptView transcript={content.transcript} />}
        </div>
      </div>

      {/* Footer */}
      <footer className="participant-footer">
        <div className="participant-footer-inner">
          <span className="participant-footer-text">
            Erstellt mit <strong>Sonora</strong> — aus dem, was wirklich gesagt wurde.
          </span>
          <a className="btn btn-primary btn-sm" href="/">
            <Icon name="mic" size={14} /> Eigene Sessions erstellen
          </a>
        </div>
      </footer>
    </div>
  );
}
