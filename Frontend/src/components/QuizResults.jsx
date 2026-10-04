import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { percent } from "../format.js";
import { BarRow } from "./charts.jsx";

// How listeners answered on their first attempt, per question and option. The correct
// option is emphasised in the "good" colour and always marked with icon and label.
export default function QuizResults({ sessionId, onShare }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api
      .quizResults(sessionId, controller.signal)
      .then(setStats)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [sessionId, reloads]);

  const refresh = (
    <div className="results-toolbar">
      <button className="btn btn-ghost btn-sm" onClick={() => setReloads((n) => n + 1)}>
        <Icon name="refresh" size={14} /> Refresh
      </button>
    </div>
  );

  if (error) {
    return (
      <div className="banner error" role="alert">
        <Icon name="alert" size={16} /> <span>{error}</span>
      </div>
    );
  }
  if (!stats) {
    return (
      <div className="stage-loading">
        <span className="proc-spinner" />
      </div>
    );
  }
  if (stats.attempts === 0) {
    return (
      <>
      {refresh}
      <div className="results-empty card">
        <Icon name="quiz" size={22} />
        <h3>No listener has taken the quiz yet</h3>
        <p>
          Share the quiz with your listeners. Each listener&apos;s first attempt is counted anonymously, and you see
          here which answers they chose.
        </p>
        {onShare && (
          <button className="btn btn-secondary btn-sm" onClick={onShare}>
            <Icon name="link" size={14} /> Share with listeners
          </button>
        )}
      </div>
      </>
    );
  }

  const perfect = stats.score_distribution[stats.total] ?? 0;
  return (
    <div className="quiz-results">
      {refresh}
      <div className="profile-stats results-stats">
        <Stat value={stats.attempts} label={stats.attempts === 1 ? "listener" : "listeners"} />
        <Stat
          value={`${stats.average_score.toFixed(1)} / ${stats.total}`}
          label={`average score · ${percent(stats.average_score, stats.total)}%`}
        />
        <Stat value={perfect} label="all answers correct" />
      </div>

      {stats.questions.map((q, i) => {
        const correct = q.option_counts[q.correct_option];
        return (
          <section className="q-card" key={i}>
            <div className="q-title">
              <span className="q-num">Q{i + 1}</span>
              <span>{q.question}</span>
            </div>
            <p className="quiz-result-rate">
              <strong>{percent(correct, q.answered)}%</strong> answered correctly
              {q.answered < stats.attempts && ` · ${stats.attempts - q.answered} skipped`}
            </p>
            <div className="bar-list">
              {q.options.map((option, oi) => {
                const isCorrect = oi === q.correct_option;
                return (
                  <BarRow
                    key={oi}
                    tone={isCorrect ? "good" : "muted"}
                    icon={
                      <span className={"q-marker" + (isCorrect ? " correct" : "")} aria-hidden="true">
                        {String.fromCharCode(65 + oi)}
                      </span>
                    }
                    label={
                      <>
                        {option}
                        {isCorrect && (
                          <span className="correct-tag">
                            <Icon name="check" size={12} /> Correct
                          </span>
                        )}
                      </>
                    }
                    value={q.option_counts[oi]}
                    max={q.answered}
                    display={`${percent(q.option_counts[oi], q.answered)}% · ${q.option_counts[oi]}`}
                    detail={`${q.option_counts[oi]} of ${q.answered} listeners chose this`}
                  />
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
