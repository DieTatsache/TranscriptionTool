import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { QuizView, ScriptView, SharedChatView, TranscriptView } from "./Results.jsx";
import FeedbackView from "./FeedbackView.jsx";

// Public page behind a share link. The server decides which tabs are visible; the token
// in the URL cannot be edited to reveal more.
const TAB_DEFS = [
  { id: "script", label: "Script", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "chat", label: "Chatbot", icon: "chat" },
  { id: "transcript", label: "Transcript", icon: "transcript" },
  { id: "feedback", label: "Feedback", icon: "star" },
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
          For trainers →
        </a>
      </nav>

      <div className="participant-body">
        {error ? (
          <div className="participant-message">
            <Icon name="alert" size={22} />
            <h2>{error.status === 404 ? "Link not available" : "Something went wrong"}</h2>
            <p>
              {error.status === 404
                ? "This link is invalid, has expired, or was revoked by the trainer."
                : error.status === 429
                  ? "Too many requests. Please try again in a minute."
                  : "The content could not be loaded. Please try again later."}
            </p>
          </div>
        ) : !share ? (
          <div className="stage-loading">
            <span className="proc-spinner" />
          </div>
        ) : (
          <>
            {share.viewer_is_owner && (
              <div className="banner info participant-owner-banner">
                <Icon name="spark" size={16} />
                <span>
                  This is your own share link. Your quiz answers and feedback here don&apos;t count towards your
                  listener statistics. To try it as a listener, open the link in a private window or another
                  browser.
                </span>
              </div>
            )}
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
              {share.tabs.includes("chat") && (
                // Stays mounted on other tabs: the conversation only lives in this page.
                <div hidden={activeTab !== "chat"}>
                  <SharedChatView token={token} script={share.script} />
                </div>
              )}
              {activeTab === "transcript" && share.transcript && <TranscriptView transcript={share.transcript} />}
              {activeTab === "feedback" && share.feedback_form && (
                <FeedbackView
                  form={share.feedback_form}
                  submitted={share.feedback_submitted}
                  isOwner={share.viewer_is_owner}
                  onSubmit={(ratings, comment) => api.submitFeedback(token, ratings, comment)}
                />
              )}
            </div>
          </>
        )}
      </div>

      <footer className="participant-footer">
        <div className="participant-footer-inner">
          <span className="participant-footer-text">
            Made with <strong>Sonora</strong> — from what was actually said.
          </span>
        </div>
      </footer>
    </div>
  );
}
