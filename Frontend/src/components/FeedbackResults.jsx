import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatDate, percent } from "../format.js";
import { BarRow } from "./charts.jsx";
import ConfirmDialog from "./ConfirmDialog.jsx";

// Owner view of the anonymous listener feedback: answer shares per question and the
// open comments, newest first.

const PAGE = 20;

function optionLabel(question, index) {
  if (question.type === "stars") return `${"★".repeat(index + 1)} ${question.options[index]}`;
  if (question.type === "scale") {
    const end = index === 0 ? question.low : index === question.options.length - 1 ? question.high : null;
    return end ? `${question.options[index]} · ${end}` : question.options[index];
  }
  return question.options[index];
}

// Ratings read best-first (5 stars at the top); choices keep their own order.
function displayOrder(question) {
  const indexes = question.options.map((_, i) => i);
  return question.type === "choice" ? indexes : indexes.reverse();
}

export default function FeedbackResults({ sessionId, onShare }) {
  const [summary, setSummary] = useState(null);
  const [comments, setComments] = useState([]);
  // Rows received so far, repeats included: the offset of the next page.
  const [fetched, setFetched] = useState(0);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let current = true;
    Promise.all([api.feedbackSummary(sessionId), api.feedbackComments(sessionId, { limit: PAGE })])
      .then(([nextSummary, firstPage]) => {
        if (!current) return;
        setSummary(nextSummary);
        setComments(firstPage);
        setFetched(firstPage.length);
        setError(null);
      })
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [sessionId, reloads]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const next = await api.feedbackComments(sessionId, { limit: PAGE, offset: fetched });
      // Comments that arrived meanwhile push older ones down, so a page can repeat some
      // already shown: skip those, and count them in the offset to keep moving forward.
      setFetched((n) => n + next.length);
      setComments((prev) => {
        const shown = new Set(prev.map((c) => c.id));
        return [...prev, ...next.filter((c) => !shown.has(c.id))];
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await api.deleteFeedback(sessionId, pendingDelete.id);
      setPendingDelete(null);
      setReloads((n) => n + 1);
    } catch (err) {
      setPendingDelete(null);
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  if (error && !summary) {
    return (
      <div className="banner error" role="alert">
        <Icon name="alert" size={16} /> <span>{error}</span>
      </div>
    );
  }
  if (!summary) {
    return (
      <div className="stage-loading">
        <span className="proc-spinner" />
      </div>
    );
  }

  return (
    <div className="feedback-results">
      <div className="quiz-head">
        <div>
          <h2>Listener feedback</h2>
          <p className="script-summary">Anonymous answers from the feedback form on your share links.</p>
        </div>
        <div className="results-head-actions">
          <span className="quiz-count">
            {summary.responses} {summary.responses === 1 ? "response" : "responses"}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={() => setReloads((n) => n + 1)}>
            <Icon name="refresh" size={14} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="banner error" role="alert">
          <Icon name="alert" size={16} /> <span>{error}</span>
        </div>
      )}

      {summary.responses === 0 ? (
        <div className="results-empty card">
          <Icon name="spark" size={22} />
          <h3>No feedback yet</h3>
          <p>
            Share the session with the feedback form switched on. Listeners answer anonymously, once per device, and
            you see the results here.
          </p>
          {onShare && (
            <button className="btn btn-secondary btn-sm" onClick={onShare}>
              <Icon name="link" size={14} /> Share with listeners
            </button>
          )}
        </div>
      ) : (
        <div className="feedback-stats">
          {summary.questions.map((q) => (
            <section className="card feedback-stat" key={q.id}>
              <div className="analysis-section-head">
                <h3>{q.label}</h3>
                {q.average != null && (
                  <span className="feedback-average">
                    Average <strong>{q.average.toFixed(1)}</strong> / {q.options.length}
                  </span>
                )}
              </div>
              <div className="bar-list">
                {displayOrder(q).map((i) => (
                  <BarRow
                    key={i}
                    label={optionLabel(q, i)}
                    value={q.counts[i]}
                    max={q.answered}
                    display={`${percent(q.counts[i], q.answered)}% · ${q.counts[i]}`}
                    detail={`${q.counts[i]} of ${q.answered} listeners`}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {summary.comments > 0 && (
        <section className="feedback-comments">
          <div className="analysis-section-head">
            <h3>Open answers</h3>
            <span>{summary.comments}</span>
          </div>
          <ul>
            {comments.map((c) => (
              <li className="feedback-comment card" key={c.id}>
                <p>{c.comment}</p>
                <div className="feedback-comment-meta">
                  <span>{formatDate(c.created_at)}</span>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setPendingDelete(c)}
                    aria-label="Remove this response"
                    title="Remove this response (e.g. spam)"
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {comments.length < summary.comments && (
            <button className="btn btn-ghost btn-sm" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? <span className="proc-spinner" /> : null} Show more
            </button>
          )}
        </section>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Remove this response?"
          confirmLabel="Remove"
          danger
          busy={deleting}
          onConfirm={remove}
          onCancel={() => setPendingDelete(null)}
        >
          The comment and the ratings of this listener are deleted permanently and no longer count in the results.
        </ConfirmDialog>
      )}
    </div>
  );
}
