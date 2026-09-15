import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";

const DEMO_STEPS = [
  { label: "Transcribing audio", detail: "Speaker separation · 42 min" },
  { label: "Extracting key points", detail: "From what was actually said" },
  { label: "Drafting the recap script", detail: "6 core points identified" },
  { label: "Generating quiz questions", detail: "Grounded in the transcript" },
  { label: "Rendering short video", detail: "Optional · ~90 sec clip" },
];

const LIVE_STEPS = [
  { label: "Processing transcript", detail: "From your recording" },
  { label: "Extracting key points", detail: "From what was actually said" },
  { label: "Drafting the recap script", detail: "Building summary" },
  { label: "Generating quiz questions", detail: "Grounded in the transcript" },
];

export default function Processing({ onDone, hasRealContent }) {
  const STEPS = hasRealContent ? LIVE_STEPS : DEMO_STEPS;
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (step >= STEPS.length) {
      const done = setTimeout(onDone, 700);
      return () => clearTimeout(done);
    }
    const id = setTimeout(() => setStep((s) => s + 1), 900);
    return () => clearTimeout(id);
  }, [step, onDone, STEPS.length]);

  const pct = Math.min(100, Math.round((step / STEPS.length) * 100));

  return (
    <div className="processing fade-up">
      <div className="proc-card">
        <div className="proc-ring">
          <Icon name="spark" size={26} />
        </div>
        <h2>Analyzing what was said</h2>
        <p className="proc-sub">
          {hasRealContent
            ? "Building your recap from what was actually recorded."
            : "Sonora works from the audio — not your slides — so the recap reflects what the room actually heard."}
        </p>

        <div className="proc-bar">
          <div className="proc-bar-fill" style={{ width: `${pct}%` }} />
        </div>

        <ul className="proc-steps">
          {STEPS.map((s, i) => {
            const state = i < step ? "done" : i === step ? "active" : "pending";
            return (
              <li key={i} className={"proc-step " + state}>
                <span className="proc-icon">
                  {state === "done" ? (
                    <Icon name="check" size={14} />
                  ) : state === "active" ? (
                    <span className="proc-spinner" />
                  ) : (
                    <span className="proc-dot" />
                  )}
                </span>
                <span className="proc-step-label">{s.label}</span>
                <span className="proc-step-detail">{s.detail}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
