import { useCallback, useEffect, useState } from "react";
import "./App.css";
import Icon from "./Icon.jsx";
import { api, onSessionExpired, setCsrfToken } from "./api.js";
import { formatDate, formatDuration, initials, isProcessing } from "./format.js";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import Landing from "./components/Landing.jsx";
import Login from "./components/Login.jsx";
import ParticipantView from "./components/ParticipantView.jsx";
import Processing from "./components/Processing.jsx";
import Profile from "./components/Profile.jsx";
import Recorder from "./components/Recorder.jsx";
import Results from "./components/Results.jsx";

// Participant share links: /share/<token>
const SHARE_PATH = /^\/share\/([A-Za-z0-9_-]{32,64})\/?$/;
const shareToken = window.location.pathname.match(SHARE_PATH)?.[1] ?? null;
const POLL_INTERVAL_MS = 3000;

export default function App() {
  if (shareToken) return <ParticipantView token={shareToken} />;
  return <TrainerApp />;
}

function TrainerApp() {
  const [view, setView] = useState("loading"); // loading | landing | login | app | profile
  const [loginMode, setLoginMode] = useState("login");
  const [user, setUser] = useState(null);
  const [meta, setMeta] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    onSessionExpired(() => {
      setUser(null);
      setCsrfToken(null);
      setNotice("Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
      setView("login");
    });
    api.meta().then(setMeta).catch(() => setMeta(null));
    api
      .me()
      .then((me) => {
        setUser(me);
        setView("app");
      })
      .catch(() => setView("landing"));
  }, []);

  const enter = (mode = "login") => {
    if (user) {
      setView("app");
      return;
    }
    setLoginMode(mode);
    setNotice(null);
    setView("login");
  };

  const handleLogin = (me) => {
    setUser(me);
    setNotice(null);
    setView("app");
  };

  const handleLogout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
    setView("login");
  };

  const handleAccountDeleted = () => {
    setUser(null);
    setView("landing");
  };

  if (view === "loading") {
    return (
      <div className="boot-screen" aria-busy="true">
        <span className="proc-spinner" />
      </div>
    );
  }
  if (view === "landing") return <Landing onEnter={enter} />;
  if (view === "login" || !user) {
    return (
      <Login mode={loginMode} onModeChange={setLoginMode} meta={meta} notice={notice} onLogin={handleLogin} />
    );
  }
  if (view === "profile") {
    return (
      <Profile
        user={user}
        meta={meta}
        onUserChange={setUser}
        onBack={() => setView("app")}
        onLogout={handleLogout}
        onDeleted={handleAccountDeleted}
      />
    );
  }
  return (
    <AppShell user={user} meta={meta} onHome={() => setView("landing")} onProfile={() => setView("profile")} />
  );
}

function AppShell({ user, meta, onHome, onProfile }) {
  const [sessions, setSessions] = useState(null); // null while loading
  const [activeId, setActiveId] = useState(null);
  const [recording, setRecording] = useState(false);
  const [usage, setUsage] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [error, setError] = useState(null);

  const refreshSessions = useCallback(async () => {
    const list = await api.listSessions();
    setSessions(list);
    return list;
  }, []);

  const refreshUsage = useCallback(() => {
    api.usage().then(setUsage).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listSessions()
      .then((list) => {
        if (cancelled) return;
        setSessions(list);
        setActiveId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        setSessions([]);
        setError(err.message);
      });
    api
      .usage()
      .then((value) => !cancelled && setUsage(value))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll only while something is being processed.
  const anyProcessing = sessions?.some(isProcessing) ?? false;
  useEffect(() => {
    if (!anyProcessing) return undefined;
    const timer = setInterval(() => refreshSessions().catch(() => {}), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [anyProcessing, refreshSessions]);

  const active = sessions?.find((s) => s.id === activeId) ?? null;

  const select = (id) => {
    setActiveId(id);
    setRecording(false);
  };

  const handleUploaded = (session) => {
    setSessions((prev) => [session, ...(prev ?? [])]);
    setActiveId(session.id);
    setRecording(false);
    refreshUsage();
  };

  const handleRetry = async (session) => {
    setError(null);
    try {
      const updated = await api.retrySession(session.id);
      setSessions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmDelete = async () => {
    const target = pendingDelete;
    setPendingDelete(null);
    try {
      await api.deleteSession(target.id);
      const next = sessions.filter((s) => s.id !== target.id);
      setSessions(next);
      if (activeId === target.id) setActiveId(next[0]?.id ?? null);
    } catch (err) {
      setError(err.message);
    }
  };

  let content;
  if (recording) {
    content = (
      <Recorder meta={meta} usage={usage} onUploaded={handleUploaded} onCancel={() => setRecording(false)} />
    );
  } else if (sessions === null) {
    content = (
      <div className="stage-loading">
        <span className="proc-spinner" />
      </div>
    );
  } else if (!active) {
    content = <EmptyState onNew={() => setRecording(true)} />;
  } else if (active.status === "ready") {
    content = <Results key={active.id} session={active} />;
  } else {
    content = (
      <Processing session={active} onRetry={() => handleRetry(active)} onDelete={() => setPendingDelete(active)} />
    );
  }

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        active={recording ? null : activeId}
        onSelect={select}
        onNew={() => setRecording(true)}
        onDelete={setPendingDelete}
        onHome={onHome}
        usage={usage}
      />

      <main className="main">
        <TopBar recording={recording} session={active} onNew={() => setRecording(true)} user={user} onProfile={onProfile} />
        <div className="stage">
          {error && (
            <div className="banner error" role="alert">
              <Icon name="alert" size={16} />
              <span>{error}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setError(null)} aria-label="Dismiss">
                <Icon name="close" size={14} />
              </button>
            </div>
          )}
          {content}
        </div>
      </main>

      {pendingDelete && (
        <ConfirmDialog
          title="Delete session?"
          confirmLabel="Delete"
          danger
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        >
          <strong>{pendingDelete.title}</strong> will be deleted permanently, including its transcript,
          recap, quiz, chat history and every share link.
        </ConfirmDialog>
      )}
    </div>
  );
}

function EmptyState({ onNew }) {
  return (
    <div className="empty-state fade-up">
      <div className="proc-ring">
        <Icon name="mic" size={26} />
      </div>
      <h2>Record your first session</h2>
      <p>
        Record a lecture in the room or upload an existing recording. Sonora turns what was said into a recap,
        a quiz and a chat you can ask about the session.
      </p>
      <button className="btn btn-primary" onClick={onNew}>
        <Icon name="mic" size={16} /> New session
      </button>
    </div>
  );
}

function Sidebar({ sessions, active, onSelect, onNew, onDelete, onHome, usage }) {
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
        {sessions?.length === 0 && <div className="session-empty">No sessions yet.</div>}
        {sessions?.map((s) => (
          <div key={s.id} className={"session-item" + (s.id === active ? " active" : "")}>
            <button className="session-item-btn" onClick={() => onSelect(s.id)}>
              <span className="session-title">{s.title}</span>
              <span className="session-meta">
                <SessionMeta session={s} />
              </span>
            </button>
            <button
              className="session-delete"
              title="Delete session"
              aria-label={`Delete ${s.title}`}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s);
              }}
            >
              <Icon name="close" size={13} />
            </button>
          </div>
        ))}
      </nav>

      <div className="side-footer">
        <PlanCard usage={usage} />
      </div>
    </aside>
  );
}

function SessionMeta({ session }) {
  if (isProcessing(session)) return <span className="session-status processing">Processing…</span>;
  if (session.status === "failed") return <span className="session-status failed">Failed</span>;
  return (
    <>
      {formatDate(session.created_at)} · {formatDuration(session.duration_seconds)} · {session.quiz_count} quiz Qs
    </>
  );
}

function PlanCard({ usage }) {
  if (!usage) return null;
  const limit = usage.plan.monthly_session_limit;
  const used = usage.sessions_this_month;
  return (
    <div className="plan-card">
      <div className="plan-top">
        <span className="plan-name">{usage.plan.name} Plan</span>
        <span className="plan-badge">Active</span>
      </div>
      {limit != null && (
        <div className="plan-bar">
          <div className="plan-bar-fill" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
        </div>
      )}
      <span className="plan-note">
        {limit != null ? `${used} of ${limit} sessions this month` : `${used} sessions this month · unlimited`}
      </span>
    </div>
  );
}

function TopBar({ recording, session, onNew, user, onProfile }) {
  let title = "Your sessions";
  if (recording) title = "New session";
  else if (session) title = isProcessing(session) ? "Analyzing what was said" : session.title;
  const sub =
    !recording && session?.status === "ready"
      ? `${formatDate(session.created_at)} · ${formatDuration(session.duration_seconds)} · generated from audio transcript`
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
        <button className="avatar" onClick={onProfile} title="Profil öffnen" aria-label="Profil öffnen">
          {initials(user?.name)}
        </button>
      </div>
    </header>
  );
}
