import { useState } from "react";
import Icon from "../Icon.jsx";

const QUESTIONS = [
  {
    id: "overall",
    label: "Overall session quality",
    type: "stars",
  },
  {
    id: "clarity",
    label: "How clearly was the content explained?",
    type: "scale",
    low: "Very unclear",
    high: "Crystal clear",
  },
  {
    id: "pace",
    label: "How was the pace of the session?",
    type: "choice",
    options: ["Too slow", "Just right", "Too fast"],
  },
  {
    id: "relevance",
    label: "How relevant was the content to you?",
    type: "scale",
    low: "Not relevant",
    high: "Extremely relevant",
  },
  {
    id: "comment",
    label: "Anything you'd like the trainer to know?",
    type: "text",
    placeholder: "Optional — your comment stays anonymous.",
  },
];

export default function FeedbackView() {
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

  const set = (id, value) => setAnswers((a) => ({ ...a, [id]: value }));

  const allRequired = QUESTIONS.filter((q) => q.type !== "text").every((q) => answers[q.id] !== undefined);

  const submit = (e) => {
    e.preventDefault();
    
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="feedback-view">
        <div className="feedback-done fade-up">
          <div className="feedback-done-icon">
            <Icon name="check" size={28} />
          </div>
          <h2>Thank you for your feedback!</h2>
          <p>Your response has been recorded anonymously and will help the trainer improve future sessions.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="feedback-view">
      <div className="feedback-head">
        <h2>Session feedback</h2>
        <p className="script-summary">
          Takes 60 seconds. Your answers are anonymous and go directly to the trainer.
        </p>
      </div>

      <form className="feedback-form" onSubmit={submit}>
        {QUESTIONS.map((q) => (
          <div className="feedback-q" key={q.id}>
            <div className="feedback-q-label">{q.label}</div>

            {q.type === "stars" && (
              <StarRating value={answers[q.id]} onChange={(v) => set(q.id, v)} />
            )}

            {q.type === "scale" && (
              <ScaleRating
                value={answers[q.id]}
                onChange={(v) => set(q.id, v)}
                low={q.low}
                high={q.high}
              />
            )}

            {q.type === "choice" && (
              <ChoiceRating
                value={answers[q.id]}
                options={q.options}
                onChange={(v) => set(q.id, v)}
              />
            )}

            {q.type === "text" && (
              <textarea
                className="field-input field-textarea feedback-textarea"
                placeholder={q.placeholder}
                value={answers[q.id] ?? ""}
                onChange={(e) => set(q.id, e.target.value)}
                rows={3}
                maxLength={800}
              />
            )}
          </div>
        ))}

        <div className="feedback-submit">
          <button type="submit" className="btn btn-primary" disabled={!allRequired}>
            <Icon name="arrow" size={16} /> Submit feedback
          </button>
          {!allRequired && (
            <span className="feedback-hint">Please answer all questions above to continue.</span>
          )}
        </div>
      </form>
    </div>
  );
}

function StarRating({ value, onChange }) {
  const [hover, setHover] = useState(null);
  const labels = ["Poor", "Fair", "Good", "Very good", "Excellent"];
  const active = hover ?? value;
  return (
    <div className="star-rating">
      <div className="star-row">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={"star-btn" + (active >= n ? " on" : "")}
            onClick={() => onChange(n)}
            onMouseEnter={() => setHover(n)}
            onMouseLeave={() => setHover(null)}
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
          >
            ★
          </button>
        ))}
      </div>
      {active != null && <span className="star-label">{labels[active - 1]}</span>}
    </div>
  );
}

function ScaleRating({ value, onChange, low, high }) {
  return (
    <div className="scale-rating">
      <div className="scale-row">
        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
          <button
            key={n}
            type="button"
            className={"scale-btn" + (value === n ? " on" : "")}
            onClick={() => onChange(n)}
            aria-label={String(n)}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="scale-labels">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  );
}

function ChoiceRating({ value, options, onChange }) {
  return (
    <div className="choice-rating">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          className={"choice-btn" + (value === opt ? " on" : "")}
          onClick={() => onChange(opt)}
        >
          {value === opt && <Icon name="check" size={13} />}
          {opt}
        </button>
      ))}
    </div>
  );
}
