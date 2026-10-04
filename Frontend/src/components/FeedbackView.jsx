import { useState } from "react";
import Icon from "../Icon.jsx";

// Listener feedback on a shared session. The questions come from the server (one form for
// every session), so what is asked, validated and reported always matches. Answers are
// anonymous and accepted once per browser.

function errorMessage(err) {
  switch (err.code) {
    case "participant_required":
      return "Please reload the page (cookies must be enabled) and try again.";
    case "feedback_closed":
      return "This session doesn't accept more feedback.";
    case "rate_limited":
      return "Too many attempts. Please wait a moment and try again.";
    case "network_error":
      return "The server could not be reached. Please check your connection.";
    default:
      return "Your feedback could not be sent. Please try again.";
  }
}

export default function FeedbackView({ form, submitted = false, isOwner = false, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [comment, setComment] = useState("");
  const [state, setState] = useState(submitted ? "done" : "form"); // form | sending | done | owner
  const [error, setError] = useState(null);

  if (isOwner || state === "owner") {
    return (
      <div className="feedback-view">
        <div className="feedback-done fade-up">
          <div className="feedback-done-icon muted">
            <Icon name="spark" size={26} />
          </div>
          <h2>This is your session</h2>
          <p>
            Feedback is collected from your listeners. You find their answers in the Feedback tab of your session. To
            try the form as a listener, open the link in a private window or another browser.
          </p>
        </div>
      </div>
    );
  }

  if (state === "done") {
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

  const closed = form.questions.filter((q) => q.type !== "text");
  const open = form.questions.find((q) => q.type === "text");
  const complete = closed.every((q) => answers[q.id] !== undefined);
  const set = (id, value) => setAnswers((a) => ({ ...a, [id]: value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!complete || state === "sending") return;
    setState("sending");
    setError(null);
    try {
      await onSubmit(answers, comment.trim() || null);
      setState("done");
    } catch (err) {
      if (err.code === "feedback_already_submitted") setState("done");
      else if (err.code === "own_session") setState("owner");
      else {
        setState("form");
        setError(errorMessage(err));
      }
    }
  };

  return (
    <div className="feedback-view">
      <div className="feedback-head">
        <h2>Session feedback</h2>
        <p className="script-summary">Takes 60 seconds. Your answers are anonymous and go directly to the trainer.</p>
      </div>

      <form className="feedback-form" onSubmit={submit}>
        {closed.map((q) => (
          <fieldset className="feedback-q" key={q.id}>
            <legend className="feedback-q-label">{q.label}</legend>
            {q.type === "stars" && (
              <StarRating
                labels={q.options}
                value={answers[q.id] !== undefined ? answers[q.id] + 1 : undefined}
                onChange={(stars) => set(q.id, stars - 1)}
              />
            )}
            {q.type === "scale" && (
              <ScaleRating
                points={q.options.length}
                value={answers[q.id] !== undefined ? answers[q.id] + 1 : undefined}
                onChange={(point) => set(q.id, point - 1)}
                low={q.low}
                high={q.high}
              />
            )}
            {q.type === "choice" && (
              <ChoiceRating options={q.options} value={answers[q.id]} onChange={(index) => set(q.id, index)} />
            )}
          </fieldset>
        ))}

        {open && (
          <div className="feedback-q">
            <label className="feedback-q-label" htmlFor="feedback-comment">
              {open.label}
            </label>
            <textarea
              id="feedback-comment"
              className="field-input field-textarea feedback-textarea"
              placeholder={open.placeholder ?? ""}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              maxLength={open.max_length ?? 800}
            />
          </div>
        )}

        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}

        <div className="feedback-submit">
          <button type="submit" className="btn btn-primary" disabled={!complete || state === "sending"}>
            {state === "sending" ? <span className="proc-spinner" /> : <Icon name="arrow" size={16} />} Submit
            feedback
          </button>
          {!complete && <span className="feedback-hint">Please answer all questions above to continue.</span>}
        </div>
      </form>
    </div>
  );
}

function StarRating({ labels, value, onChange }) {
  const [hover, setHover] = useState(null);
  const active = hover ?? value;
  return (
    <div className="star-rating">
      <div className="star-row">
        {labels.map((label, i) => {
          const stars = i + 1;
          return (
            <button
              key={stars}
              type="button"
              className={"star-btn" + (active >= stars ? " on" : "")}
              onClick={() => onChange(stars)}
              onMouseEnter={() => setHover(stars)}
              onMouseLeave={() => setHover(null)}
              aria-label={`${stars} star${stars > 1 ? "s" : ""}: ${label}`}
              aria-pressed={value === stars}
            >
              ★
            </button>
          );
        })}
      </div>
      {active != null && <span className="star-label">{labels[active - 1]}</span>}
    </div>
  );
}

function ScaleRating({ points, value, onChange, low, high }) {
  return (
    <div className="scale-rating">
      <div className="scale-row">
        {Array.from({ length: points }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            type="button"
            className={"scale-btn" + (value === n ? " on" : "")}
            onClick={() => onChange(n)}
            aria-label={`${n} of ${points}`}
            aria-pressed={value === n}
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

function ChoiceRating({ options, value, onChange }) {
  return (
    <div className="choice-rating">
      {options.map((option, i) => (
        <button
          key={option}
          type="button"
          className={"choice-btn" + (value === i ? " on" : "")}
          onClick={() => onChange(i)}
          aria-pressed={value === i}
        >
          {value === i && <Icon name="check" size={13} />}
          {option}
        </button>
      ))}
    </div>
  );
}
