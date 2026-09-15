import { useEffect, useRef, useState } from "react";
import Icon from "../Icon.jsx";
import {
  CHAT_ANSWERS,
  CHAT_FALLBACK,
  CHAT_SUGGESTIONS,
  SESSION_CONTENT,
} from "../data.js";

const TABS = [
  { id: "script", label: "Script", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "video", label: "Video", icon: "video" },
  { id: "chat", label: "Chatbot", icon: "chat" },
  { id: "transcript", label: "Transcript", icon: "transcript" },
];

// Fall back to s1 demo data for dynamically created sessions.
function getSessionContent(sessionId, liveContent) {
  if (liveContent?.[sessionId]) return liveContent[sessionId];
  return SESSION_CONTENT[sessionId] ?? SESSION_CONTENT.s1;
}

export default function Results({ sessionId, liveContent }) {
  const [tab, setTab] = useState("script");
  const [shareOpen, setShareOpen] = useState(false);

  // Reset to script tab when switching sessions.
  useEffect(() => { setTab("script"); }, [sessionId]);

  const content = getSessionContent(sessionId, liveContent);
  const isLive = !!liveContent?.[sessionId];
  const visibleTabs = isLive ? TABS.filter((t) => t.id !== "video") : TABS;

  return (
    <div className="results fade-up">
      <div className="tabs">
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            className={"tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            <Icon name={t.icon} size={16} />
            {t.label}
          </button>
        ))}
      </div>

      <div className="tab-panel">
        {tab === "script" && (
          <ScriptView
            script={content.script}
            onShare={() => setShareOpen(true)}
          />
        )}
        {tab === "quiz" && <QuizView quiz={content.quiz} key={sessionId} />}
        {tab === "video" && !isLive && <VideoView />}
        {tab === "chat" && <ChatView key={sessionId} transcript={content.transcript} />}
        {tab === "transcript" && <TranscriptView transcript={content.transcript} />}
      </div>

      {shareOpen && (
        <ShareModal
          sessionId={sessionId}
          onClose={() => setShareOpen(false)}
        />
      )}
    </div>
  );
}

// ---- Share Modal ----

const SHARE_TAB_OPTIONS = [
  { id: "script", label: "Script & Zusammenfassung", icon: "script" },
  { id: "quiz", label: "Quiz", icon: "quiz" },
  { id: "video", label: "Video (90-Sek.-Recap)", icon: "video" },
  { id: "transcript", label: "Transkript", icon: "transcript" },
];

function ShareModal({ sessionId, onClose }) {
  const [selected, setSelected] = useState(["script", "quiz", "video", "transcript"]);
  const [copied, setCopied] = useState(false);

  const toggle = (id) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );

  const shareUrl =
    window.location.origin +
    "/?session=" +
    sessionId +
    "&tabs=" +
    SHARE_TAB_OPTIONS.filter((t) => selected.includes(t.id))
      .map((t) => t.id)
      .join(",");

  const copyLink = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Mit Teilnehmern teilen</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <p className="modal-sub">
          Wähle aus, welche Inhalte die Teilnehmer sehen dürfen. Sie brauchen
          keinen Account — nur den Link.
        </p>

        <div className="share-tab-list">
          {SHARE_TAB_OPTIONS.map((opt) => (
            <label key={opt.id} className={"share-tab-row" + (selected.includes(opt.id) ? " checked" : "")}>
              <input
                type="checkbox"
                checked={selected.includes(opt.id)}
                onChange={() => toggle(opt.id)}
              />
              <Icon name={opt.icon} size={16} />
              <span>{opt.label}</span>
              <span className={"share-check" + (selected.includes(opt.id) ? " on" : "")}>
                <Icon name="check" size={13} />
              </span>
            </label>
          ))}
        </div>

        <div className="share-url-row">
          <div className="share-url-box">{shareUrl}</div>
          <button
            className={"btn btn-primary btn-sm" + (copied ? " copied" : "")}
            onClick={copyLink}
            disabled={selected.length === 0}
          >
            <Icon name={copied ? "check" : "copy"} size={15} />
            {copied ? "Kopiert!" : "Link kopieren"}
          </button>
        </div>

        {selected.length === 0 && (
          <p className="share-warn">Bitte wähle mindestens einen Inhalt aus.</p>
        )}
      </div>
    </div>
  );
}

// ---- Exported sub-views (reused in ParticipantView) ----

export function ScriptView({ script, onShare }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = [script.title, "", script.summary, "", ...script.overview, "", "Key takeaways:", ...script.takeaways.map((t) => `• ${t.text} (${t.at})`)].join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
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
                <span className="point-at">{t.at}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}

export function QuizView({ quiz }) {
  const [answers, setAnswers] = useState({});
  const [checked, setChecked] = useState(false);

  const score = quiz.reduce(
    (acc, q, i) => acc + (answers[i] === q.correct ? 1 : 0),
    0
  );
  const allAnswered = Object.keys(answers).length === quiz.length;

  return (
    <div className="quiz-view">
      <div className="quiz-head">
        <div>
          <h2>Auto-generated quiz</h2>
          <p className="script-summary">
            Every question is grounded in a specific moment of the session — with a timestamp you can
            verify.
          </p>
        </div>
        {checked ? (
          <div className={"quiz-score" + (score === quiz.length ? " perfect" : "")}>
            {score} / {quiz.length} correct
          </div>
        ) : (
          <span className="quiz-count">{quiz.length} questions</span>
        )}
      </div>

      {quiz.map((q, i) => (
        <div className="q-card" key={i}>
          <div className="q-title">
            <span className="q-num">Q{i + 1}</span>
            {q.q}
          </div>
          <div className="q-options">
            {q.options.map((opt, oi) => {
              const selected = answers[i] === oi;
              let cls = "q-opt";
              if (checked) {
                if (oi === q.correct) cls += " correct";
                else if (selected) cls += " wrong";
              } else if (selected) cls += " selected";
              return (
                <button
                  key={oi}
                  className={cls}
                  disabled={checked}
                  onClick={() => setAnswers((a) => ({ ...a, [i]: oi }))}
                >
                  <span className="q-marker">{String.fromCharCode(65 + oi)}</span>
                  {opt}
                  {checked && oi === q.correct && <Icon name="check" size={15} style={{ marginLeft: "auto" }} />}
                </button>
              );
            })}
          </div>
          {checked && (
            <div className="q-explain">
              <Icon name="wave" size={14} />
              <span>{q.why}</span>
              <span className="point-at">said at {q.source}</span>
            </div>
          )}
        </div>
      ))}

      <div className="quiz-footer">
        {!checked ? (
          <button
            className="btn btn-primary"
            disabled={!allAnswered}
            onClick={() => setChecked(true)}
          >
            Check answers
          </button>
        ) : (
          <button
            className="btn btn-ghost"
            onClick={() => {
              setChecked(false);
              setAnswers({});
            }}
          >
            <Icon name="refresh" size={15} /> Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function VideoView() {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(34);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) { setPlaying(false); return 100; }
        return p + 1;
      });
    }, 500);
    return () => clearInterval(id);
  }, [playing]);

  const totalSecs = 88;
  const elapsed = Math.round((progress / 100) * totalSecs);
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="video-view">
      <div className="video-stage">
        <div className="video-frame">
          <div className="video-overlay">
            <button className="video-play" onClick={() => setPlaying((p) => !p)}>
              <Icon name={playing ? "pause" : "play"} size={26} />
            </button>
          </div>
          <div className="video-captions">
            "An objection is not a rejection — it's a request for more information."
          </div>
          <div className="video-progress" onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setProgress(Math.round(((e.clientX - rect.left) / rect.width) * 100));
          }}>
            <div className="video-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="video-time">{fmt(elapsed)} / {fmt(totalSecs)}</div>
        </div>
        <span className="video-badge">
          <Icon name="spark" size={13} /> Beta
        </span>
      </div>

      <div className="video-side">
        <h2>90-second recap video</h2>
        <p className="script-summary">
          A short, shareable clip that strings together the session's key moments — captioned with the
          trainer's own words.
        </p>
        <ul className="video-scenes">
          {["Opening reframe", "The three-step sequence", '"Let silence do the work"', "Homework & close"].map(
            (s, i) => (
              <li key={i}>
                <span className="scene-num">{i + 1}</span>
                {s}
              </li>
            )
          )}
        </ul>
        <div className="video-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="arrow" size={15} /> Download MP4
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => { setProgress(0); setPlaying(false); }}>
            <Icon name="refresh" size={15} /> Regenerate
          </button>
        </div>
      </div>
    </div>
  );
}

export function TranscriptView({ transcript }) {
  const [exported, setExported] = useState(false);

  const handleExport = () => {
    const text = transcript.map((l) => `[${l.t}] ${l.speaker}: ${l.text}`).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setExported(true);
      setTimeout(() => setExported(false), 2000);
    });
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
            <span className="feed-time">{l.t}</span>
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

// ---- Chat (trainer-only, not exported for participants) ----

function ChatView({ transcript }) {
  const isLive = transcript && !transcript.some((l) => l.speaker === "Trainer");

  const [messages, setMessages] = useState([
    {
      role: "bot",
      source: "lesson",
      text: isLive
        ? "Hi! Ask me anything about what was said in this recording. I'll search through the transcript to find the answer."
        : "Hi! Ask me anything about this session. I'll answer from what was actually said in the lesson — and if it wasn't covered, I'll tell you and pull from the web or general knowledge instead.",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = (raw) => {
    const q = (raw ?? input).trim();
    if (!q || thinking) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setThinking(true);

    setTimeout(() => {
      setThinking(false);
      const reply = answerQuestion(q, transcript, isLive);
      setMessages((m) => [...m, { role: "bot", source: reply.source, text: reply.answer, cite: reply.cite }]);
    }, 850);
  };

  return (
    <div className="chat-view">
      <div className="quiz-head">
        <div>
          <h2>Ask the session</h2>
          <p className="script-summary">
            A chatbot that knows this lesson. It answers from the transcript first — and is honest when
            an answer comes from the web or its own knowledge instead.
          </p>
        </div>
      </div>

      <div className="chat-box">
        <div className="chat-body" ref={bodyRef}>
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div className="chat-row user" key={i}>
                <div className="chat-bubble user">{m.text}</div>
              </div>
            ) : (
              <div className="chat-row bot" key={i}>
                <div className="chat-avatar">
                  <Icon name="spark" size={15} />
                </div>
                <div className="chat-bot-col">
                  <SourceTag source={m.source} cite={m.cite} />
                  <div className="chat-bubble bot" dangerouslySetInnerHTML={{ __html: renderBold(m.text) }} />
                </div>
              </div>
            )
          )}
          {thinking && (
            <div className="chat-row bot">
              <div className="chat-avatar">
                <Icon name="spark" size={15} />
              </div>
              <div className="chat-typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}
        </div>

        <div className="chat-suggest">
          {CHAT_SUGGESTIONS.map((s) => (
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
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about this session…"
          />
          <button type="submit" className="btn btn-primary btn-sm" disabled={!input.trim() || thinking}>
            <Icon name="arrow" size={15} /> Ask
          </button>
        </form>
      </div>
    </div>
  );
}

function answerQuestion(q, transcript, isLive) {
  if (isLive && transcript?.length) {
    const lower = q.toLowerCase();
    const words = lower.split(/\s+/).filter((w) => w.length > 3);
    const scored = transcript.map((line) => {
      const lineText = line.text.toLowerCase();
      const score = words.filter((w) => lineText.includes(w)).length;
      return { line, score };
    }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score);

    if (scored.length > 0) {
      const best = scored[0].line;
      const nearby = scored.slice(0, 3).map((x) => x.line.text).join(" … ");
      return {
        source: "lesson",
        cite: best.t,
        answer: `At **${best.t}**, this was said: "${nearby}"`,
      };
    }

    return {
      source: "knowledge",
      cite: null,
      answer: "I couldn't find a direct match for that in the transcript. Could you rephrase, or ask about something that was explicitly said?",
    };
  }

  const lower = q.toLowerCase();
  const hit = CHAT_ANSWERS.find((a) => a.match.some((k) => lower.includes(k)));
  return hit ?? CHAT_FALLBACK;
}

function SourceTag({ source, cite }) {
  const map = {
    lesson: { label: cite ? `From the lesson · ${cite}` : "From the lesson", cls: "lesson", icon: "wave" },
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

function renderBold(text) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
