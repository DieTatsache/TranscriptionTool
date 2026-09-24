import Icon from "../Icon.jsx";

// Live progress of a session on the server (the parent polls its status).
const STEPS = [
  { status: "uploaded", label: "Recording uploaded", detail: "Stored for processing" },
  { status: "queued", label: "Waiting for a free worker", detail: "Usually starts within seconds" },
  { status: "transcribing", label: "Transcribing audio", detail: "Speech-to-text on our servers" },
  { status: "generating", label: "Writing the recap & quiz", detail: "Grounded in the transcript" },
];
const POSITION = { queued: 1, transcribing: 2, generating: 3 };

export default function Processing({ session, onRetry, onDelete }) {
  if (session.status === "failed") {
    return (
      <div className="processing fade-up">
        <div className="proc-card">
          <div className="proc-ring failed">
            <Icon name="alert" size={26} />
          </div>
          <h2>Processing failed</h2>
          <p className="proc-sub">{session.error_message ?? "Something went wrong while analyzing the recording."}</p>
          <div className="proc-actions">
            <button className="btn btn-primary" onClick={onRetry}>
              <Icon name="refresh" size={15} /> Try again
            </button>
            <button className="btn btn-ghost" onClick={onDelete}>
              <Icon name="trash" size={15} /> Delete
            </button>
          </div>
        </div>
      </div>
    );
  }

  const current = POSITION[session.status] ?? 1;
  const pct = Math.round((current / STEPS.length) * 100);

  return (
    <div className="processing fade-up">
      <div className="proc-card" aria-live="polite">
        <div className="proc-ring">
          <Icon name="spark" size={26} />
        </div>
        <h2>Analyzing what was said</h2>
        <p className="proc-sub">
          Sonora works from the audio — not your slides — so the recap reflects what the room actually heard. You can
          leave this page; processing continues on the server.
        </p>

        <div className="proc-bar">
          <div className="proc-bar-fill" style={{ width: `${pct}%` }} />
        </div>

        <ul className="proc-steps">
          {STEPS.map((step, i) => {
            const state = i < current ? "done" : i === current ? "active" : "pending";
            return (
              <li key={step.status} className={"proc-step " + state}>
                <span className="proc-icon">
                  {state === "done" ? (
                    <Icon name="check" size={14} />
                  ) : state === "active" ? (
                    <span className="proc-spinner" />
                  ) : (
                    <span className="proc-dot" />
                  )}
                </span>
                <span className="proc-step-label">{step.label}</span>
                <span className="proc-step-detail">{step.detail}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
