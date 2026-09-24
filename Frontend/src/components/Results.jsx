import { useEffect, useRef, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { FEATURES } from "../features.js";
import { boldSegments, copyToClipboard, formatDate, formatTimestamp } from "../format.js";

const TABS = [
  { id: "script", label: "Script", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "video", label: "Video", icon: "video", feature: "video" },
  { id: "chat", label: "Chatbot", icon: "chat" },
  { id: "transcript", label: "Transcript", icon: "transcript" },
];
const VISIBLE_TABS = TABS.filter((t) => !t.feature || FEATURES[t.feature]);

const DEFAULT_SUGGESTIONS = [
  "Summarize the key points",
  "What should I remember most?",
  "Explain the main idea in simple terms",
];

// Keyed by session id in the parent, so all state resets when switching sessions.
export default function Results({ session }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("script");
  const [shareOpen, setShareOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getSession(session.id, controller.signal)
      .then(setDetail)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [session.id]);

  if (error) {
    return (
      <div className="banner error" role="alert">
        <Icon name="alert" size={16} /> <span>{error}</span>
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="stage-loading">
        <span className="proc-spinner" />
      </div>
    );
  }

  return (
    <div className="results fade-up">
      <div className="tabs" role="tablist">
        {VISIBLE_TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={"tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            <Icon name={t.icon} size={16} />
            {t.label}
          </button>
        ))}
      </div>

      <div className="tab-panel">
        {tab === "script" && detail.script && <ScriptView script={detail.script} onShare={() => setShareOpen(true)} />}
        {tab === "quiz" && detail.quiz && (
          <QuizView quiz={detail.quiz} onCheck={(answers) => api.checkQuiz(session.id, answers)} />
        )}
        {tab === "video" && <VideoView />}
        {tab === "chat" && (
          <ChatView
            sessionId={session.id}
            suggestions={detail.script?.questions?.length ? detail.script.questions : DEFAULT_SUGGESTIONS}
          />
        )}
        {tab === "transcript" && detail.transcript && <TranscriptView transcript={detail.transcript} />}
      </div>

      {shareOpen && <ShareModal sessionId={session.id} onClose={() => setShareOpen(false)} />}
    </div>
  );
}

// ---- Share Modal ----

const SHARE_TAB_OPTIONS = [
  { id: "script", label: "Script & Zusammenfassung", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "transcript", label: "Transkript", icon: "transcript" },
];
const EXPIRY_OPTIONS = [
  { days: 7, label: "7 Tage" },
  { days: 30, label: "30 Tage" },
  { days: 90, label: "90 Tage" },
  { days: null, label: "Unbegrenzt" },
];
const TAB_LABELS = { script: "Script", quiz: "Quiz", transcript: "Transkript" };

function shareUrl(token) {
  return `${window.location.origin}/share/${token}`;
}

function ShareModal({ sessionId, onClose }) {
  const [selected, setSelected] = useState(["script", "quiz", "transcript"]);
  const [expiry, setExpiry] = useState(30);
  const [links, setLinks] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .listShares(sessionId)
      .then(setLinks)
      .catch((err) => {
        setLinks([]);
        setError(err.message);
      });
  }, [sessionId]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (tabId) =>
    setSelected((prev) => (prev.includes(tabId) ? prev.filter((x) => x !== tabId) : [...prev, tabId]));

  const copy = async (link) => {
    if (await copyToClipboard(shareUrl(link.token))) {
      setCopiedId(link.id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const link = await api.createShare(sessionId, selected, expiry);
      setLinks((prev) => [link, ...(prev ?? [])]);
      await copy(link);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (link) => {
    setError(null);
    try {
      await api.revokeShare(sessionId, link.id);
      setLinks((prev) => prev.filter((l) => l.id !== link.id));
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card modal-wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="share-title">Mit Teilnehmern teilen</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Schließen">
            <Icon name="close" size={16} />
          </button>
        </div>
        <p className="modal-sub">
          Wähle aus, welche Inhalte die Teilnehmer sehen dürfen. Sie brauchen keinen Account — nur den Link. Du
          kannst Links jederzeit widerrufen.
        </p>

        <div className="share-tab-list">
          {SHARE_TAB_OPTIONS.map((opt) => (
            <label key={opt.id} className={"share-tab-row" + (selected.includes(opt.id) ? " checked" : "")}>
              <input type="checkbox" checked={selected.includes(opt.id)} onChange={() => toggle(opt.id)} />
              <Icon name={opt.icon} size={16} />
              <span>{opt.label}</span>
              <span className={"share-check" + (selected.includes(opt.id) ? " on" : "")}>
                <Icon name="check" size={13} />
              </span>
            </label>
          ))}
        </div>

        <div className="share-url-row">
          <label className="share-expiry">
            <span>Gültig</span>
            <select
              className="field-input"
              value={expiry ?? "never"}
              onChange={(e) => setExpiry(e.target.value === "never" ? null : Number(e.target.value))}
            >
              {EXPIRY_OPTIONS.map((o) => (
                <option key={o.label} value={o.days ?? "never"}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary btn-sm" onClick={create} disabled={selected.length === 0 || busy}>
            <Icon name="link" size={15} /> Link erstellen & kopieren
          </button>
        </div>
        {selected.length === 0 && <p className="share-warn">Bitte wähle mindestens einen Inhalt aus.</p>}
        {error && <p className="share-warn">{error}</p>}

        <div className="share-links">
          <div className="side-label">Aktive Links</div>
          {links === null && <span className="proc-spinner" />}
          {links?.length === 0 && <p className="share-empty">Noch keine Links erstellt.</p>}
          {links?.map((link) => (
            <div className="share-link" key={link.id}>
              <div className="share-link-info">
                <span className="share-link-tabs">{link.tabs.map((t) => TAB_LABELS[t] ?? t).join(" · ")}</span>
                <span className="share-link-meta">
                  erstellt {formatDate(link.created_at, "de-DE")} ·{" "}
                  {link.expires_at ? `gültig bis ${formatDate(link.expires_at, "de-DE")}` : "unbegrenzt gültig"}
                </span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => copy(link)}>
                <Icon name={copiedId === link.id ? "check" : "copy"} size={14} />
                {copiedId === link.id ? "Kopiert!" : "Kopieren"}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => revoke(link)} title="Link widerrufen">
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- Views shared with the participant page ----

export function ScriptView({ script, onShare }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const lines = script.takeaways.map(
      (t) => `• ${t.text}${t.at_seconds != null ? ` (${formatTimestamp(t.at_seconds)})` : ""}`,
    );
    const text = [script.title, "", script.summary, "", ...script.overview, "", "Key takeaways:", ...lines].join("\n");
    if (await copyToClipboard(text)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="script-view">
      <div className="script-head">
        <div>
          <h2>{script.title}</h2>
          <p className="script-summary">{script.summary}</p>
        </div>
        <div className="script-actions">
          <button className="btn btn-ghost btn-sm" onClick={handleCopy}>
            <Icon name={copied ? "check" : "copy"} size={15} /> {copied ? "Copied!" : "Copy"}
          </button>
          {onShare && (
            <button className="btn btn-secondary btn-sm" onClick={onShare}>
              <Icon name="arrow" size={15} /> Share with participants
            </button>
          )}
        </div>
      </div>

      <div className="script-layout">
        <article className="script-overview">
          {script.overview.map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </article>

        <aside className="script-rail">
          <div className="rail-head">
            <Icon name="spark" size={15} /> Key takeaways
          </div>
          <ul>
            {script.takeaways.map((t, i) => (
              <li key={i}>
                <span className="rail-dot" />
                <span className="rail-text">{t.text}</span>
                {t.at_seconds != null && <span className="point-at">{formatTimestamp(t.at_seconds)}</span>}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}

// Answers are graded by the server; the correct options are never sent beforehand.
export function QuizView({ quiz, onCheck }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(null);

  const allAnswered = quiz.every((_, i) => answers[i] !== undefined);

  const check = async () => {
    setChecking(true);
    setError(null);
    try {
      setResult(await onCheck(quiz.map((_, i) => answers[i] ?? null)));
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  const reset = () => {
    setResult(null);
    setAnswers({});
  };

  return (
    <div className="quiz-view">
      <div className="quiz-head">
        <div>
          <h2>Auto-generated quiz</h2>
          <p className="script-summary">
            Every question is grounded in a specific moment of the session — with a timestamp you can verify.
          </p>
        </div>
        {result ? (
          <div className={"quiz-score" + (result.score === result.total ? " perfect" : "")}>
            {result.score} / {result.total} correct
          </div>
        ) : (
          <span className="quiz-count">{quiz.length} questions</span>
        )}
      </div>

      {quiz.map((q, i) => {
        const graded = result?.results[i];
        return (
          <div className="q-card" key={i}>
            <div className="q-title">
              <span className="q-num">Q{i + 1}</span>
              {q.question}
            </div>
            <div className="q-options">
              {q.options.map((opt, oi) => {
                const selected = answers[i] === oi;
                let cls = "q-opt";
                if (graded) {
                  if (oi === graded.correct_option) cls += " correct";
                  else if (selected) cls += " wrong";
                } else if (selected) cls += " selected";
                return (
                  <button
                    key={oi}
                    className={cls}
                    disabled={!!graded || checking}
                    onClick={() => setAnswers((a) => ({ ...a, [i]: oi }))}
                  >
                    <span className="q-marker">{String.fromCharCode(65 + oi)}</span>
                    {opt}
                    {graded && oi === graded.correct_option && (
                      <Icon name="check" size={15} style={{ marginLeft: "auto" }} />
                    )}
                  </button>
                );
              })}
            </div>
            {graded && (graded.explanation || graded.source_seconds != null) && (
              <div className="q-explain">
                <Icon name="wave" size={14} />
                <span>{graded.explanation}</span>
                {graded.source_seconds != null && (
                  <span className="point-at">said at {formatTimestamp(graded.source_seconds)}</span>
                )}
              </div>
            )}
          </div>
        );
      })}

      {error && (
        <div className="banner error" role="alert">
          <Icon name="alert" size={16} /> <span>{error}</span>
        </div>
      )}
      <div className="quiz-footer">
        {!result ? (
          <button className="btn btn-primary" disabled={!allAnswered || checking} onClick={check}>
            {checking ? <span className="proc-spinner" /> : null} Check answers
          </button>
        ) : (
          <button className="btn btn-ghost" onClick={reset}>
            <Icon name="refresh" size={15} /> Try again
          </button>
        )}
      </div>
    </div>
  );
}

// Design mock of the planned recap video; only shown with VITE_FEATURE_VIDEO=true.
export function VideoView() {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(34);

  useEffect(() => {
    if (!playing) return undefined;
    const timer = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          setPlaying(false);
          return 100;
        }
        return p + 1;
      });
    }, 500);
    return () => clearInterval(timer);
  }, [playing]);

  const totalSecs = 88;
  const elapsed = Math.round((progress / 100) * totalSecs);
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="video-view">
      <div className="video-stage">
        <div className="video-frame">
          <div className="video-overlay">
            <button className="video-play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause" : "Play"}>
              <Icon name={playing ? "pause" : "play"} size={26} />
            </button>
          </div>
          <div className="video-captions">
            &quot;An objection is not a rejection — it&apos;s a request for more information.&quot;
          </div>
          <div
            className="video-progress"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              setProgress(Math.round(((e.clientX - rect.left) / rect.width) * 100));
            }}
          >
            <div className="video-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="video-time">
            {fmt(elapsed)} / {fmt(totalSecs)}
          </div>
        </div>
        <span className="video-badge">
          <Icon name="spark" size={13} /> Beta
        </span>
      </div>

      <div className="video-side">
        <h2>90-second recap video</h2>
        <p className="script-summary">
          A short, shareable clip that strings together the session&apos;s key moments — captioned with the
          trainer&apos;s own words.
        </p>
        <ul className="video-scenes">
          {["Opening reframe", "The three-step sequence", '"Let silence do the work"', "Homework & close"].map((s, i) => (
            <li key={i}>
              <span className="scene-num">{i + 1}</span>
              {s}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function TranscriptView({ transcript }) {
  const [exported, setExported] = useState(false);

  const handleExport = async () => {
    const text = transcript.map((l) => `[${formatTimestamp(l.start)}] ${l.speaker}: ${l.text}`).join("\n");
    if (await copyToClipboard(text)) {
      setExported(true);
      setTimeout(() => setExported(false), 2000);
    }
  };

  return (
    <div className="transcript-view">
      <div className="quiz-head">
        <div>
          <h2>Full transcript</h2>
          <p className="script-summary">
            The source of truth. Every script point and quiz question links back to a line here.
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={handleExport}>
          <Icon name={exported ? "check" : "copy"} size={15} /> {exported ? "Copied!" : "Export"}
        </button>
      </div>
      <div className="transcript-lines">
        {transcript.map((l, i) => (
          <div className="t-line" key={i}>
            <span className="feed-time">{formatTimestamp(l.start)}</span>
            <div>
              <span className={"feed-speaker " + l.speaker.toLowerCase()}>{l.speaker}</span>
              <p>{l.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- Chat (trainer-only; not offered to participants) ----

function ChatView({ sessionId, suggestions }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState(null);
  const bodyRef = useRef(null);
  const pendingIds = useRef(0);

  useEffect(() => {
    api
      .chatHistory(sessionId)
      .then(setMessages)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (raw) => {
    const question = (raw ?? input).trim();
    if (!question || thinking) return;
    pendingIds.current += 1;
    const pending = { id: `pending-${pendingIds.current}`, role: "user", content: question };
    setMessages((m) => [...m, pending]);
    setInput("");
    setError(null);
    setThinking(true);
    try {
      const reply = await api.askChat(sessionId, question);
      setMessages((m) => [...m, reply]);
    } catch (err) {
      setMessages((m) => m.filter((x) => x !== pending));
      setInput(question);
      setError(err.message);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="chat-view">
      <div className="quiz-head">
        <div>
          <h2>Ask the session</h2>
          <p className="script-summary">
            A chatbot that knows this lesson. It answers from the transcript first — and is honest when an answer
            comes from its general knowledge instead.
          </p>
        </div>
      </div>

      <div className="chat-box">
        <div className="chat-body" ref={bodyRef}>
          <BotMessage
            source="lesson"
            text="Hi! Ask me anything about this session. I'll answer from what was actually said in the lesson — and if it wasn't covered, I'll tell you and answer from general knowledge instead."
          />
          {loading && <span className="proc-spinner" />}
          {messages.map((m) =>
            m.role === "user" ? (
              <div className="chat-row user" key={m.id}>
                <div className="chat-bubble user">{m.content}</div>
              </div>
            ) : (
              <BotMessage key={m.id} source={m.source} cite={m.cite_seconds} text={m.content} />
            ),
          )}
          {thinking && (
            <div className="chat-row bot">
              <div className="chat-avatar">
                <Icon name="spark" size={15} />
              </div>
              <div className="chat-typing" aria-label="Thinking">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="chat-error" role="alert">
            <Icon name="alert" size={14} /> {error}
          </div>
        )}

        <div className="chat-suggest">
          {suggestions.map((s) => (
            <button key={s} className="chat-chip" onClick={() => send(s)} disabled={thinking}>
              {s}
            </button>
          ))}
        </div>

        <form
          className="chat-input"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            value={input}
            maxLength={1000}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about this session…"
            aria-label="Your question"
          />
          <button type="submit" className="btn btn-primary btn-sm" disabled={!input.trim() || thinking}>
            <Icon name="arrow" size={15} /> Ask
          </button>
        </form>
      </div>
    </div>
  );
}

function BotMessage({ source, cite, text }) {
  return (
    <div className="chat-row bot">
      <div className="chat-avatar">
        <Icon name="spark" size={15} />
      </div>
      <div className="chat-bot-col">
        <SourceTag source={source} cite={cite} />
        <div className="chat-bubble bot">
          <BoldText text={text} />
        </div>
      </div>
    </div>
  );
}

// Renders **bold** from model output as React elements — never as HTML.
function BoldText({ text }) {
  return boldSegments(text).map((segment, i) =>
    segment.bold ? <strong key={i}>{segment.text}</strong> : <span key={i}>{segment.text}</span>,
  );
}

function SourceTag({ source, cite }) {
  const map = {
    lesson: {
      label: cite != null ? `From the lesson · ${formatTimestamp(cite)}` : "From the lesson",
      cls: "lesson",
      icon: "wave",
    },
    web: { label: "Not in the lesson · answered from the web", cls: "web", icon: "arrow" },
    knowledge: { label: "Not in the lesson · general knowledge", cls: "knowledge", icon: "spark" },
  };
  const s = map[source] || map.lesson;
  return (
    <span className={"source-tag " + s.cls}>
      <Icon name={s.icon} size={12} /> {s.label}
    </span>
  );
}
