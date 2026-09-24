import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { QuizView, ScriptView, TranscriptView } from "./Results.jsx";

// Public page behind a share link. The server decides which tabs are visible; the token
// in the URL cannot be edited to reveal more.
const TAB_DEFS = [
  { id: "script", label: "Script", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "transcript", label: "Transcript", icon: "transcript" },
];

export default function ParticipantView({ token }) {
  const [share, setShare] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(null);

  useEffect(() => {
    api
      .publicShare(token)
      .then((data) => {
        setShare(data);
        setActiveTab(data.tabs[0] ?? null);
      })
      .catch(setError);
  }, [token]);

  const visibleTabs = TAB_DEFS.filter((t) => share?.tabs.includes(t.id));

  return (
    <div className="participant-page">
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
        <div className="participant-session-title">{share?.title ?? ""}</div>
        <a className="btn btn-ghost btn-sm participant-cta" href="/">
          Für Trainer →
        </a>
      </nav>

      <div className="participant-body">
        {error ? (
          <div className="participant-message">
            <Icon name="alert" size={22} />
            <h2>{error.status === 404 ? "Link nicht verfügbar" : "Etwas ist schiefgelaufen"}</h2>
            <p>
              {error.status === 404
                ? "Dieser Link ist ungültig, abgelaufen oder wurde vom Trainer widerrufen."
                : error.status === 429
                  ? "Zu viele Anfragen. Bitte versuche es in einer Minute erneut."
                  : "Die Inhalte konnten nicht geladen werden. Bitte versuche es später erneut."}
            </p>
          </div>
        ) : !share ? (
          <div className="stage-loading">
            <span className="proc-spinner" />
          </div>
        ) : (
          <>
            <div className="tabs" role="tablist">
              {visibleTabs.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={activeTab === t.id}
                  className={"tab" + (activeTab === t.id ? " active" : "")}
                  onClick={() => setActiveTab(t.id)}
                >
                  <Icon name={t.icon} size={16} />
                  {t.label}
                </button>
              ))}
            </div>
            <div className="tab-panel">
              {activeTab === "script" && share.script && <ScriptView script={share.script} />}
              {activeTab === "quiz" && share.quiz && (
                <QuizView quiz={share.quiz} onCheck={(answers) => api.checkSharedQuiz(token, answers)} />
              )}
              {activeTab === "transcript" && share.transcript && <TranscriptView transcript={share.transcript} />}
            </div>
          </>
        )}
      </div>

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
