import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatDuration, formatTimestamp, percent } from "../format.js";
import { BarRow, RadarChart } from "./charts.jsx";

// Owner-only lecture analysis: content, rhetoric and structure scored 1-10, and the time
// spent per topic. Generated in the background after processing; polled while running.

const POLL_MS = 4000;
const CATEGORIES = [
  { key: "content", label: "Content", hint: "Substance, accuracy, explanations and examples" },
  { key: "rhetoric", label: "Rhetoric", hint: "Language, engagement, filler words and pace" },
  { key: "structure", label: "Structure", hint: "Opening, order, transitions and summary" },
];
const PENDING = ["queued", "running"];

export default function AnalysisView({ sessionId }) {
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);
  const [requesting, setRequesting] = useState(false);
  const controller = useRef(null);

  const load = useCallback(async () => {
    controller.current?.abort();
    controller.current = new AbortController();
    try {
      setAnalysis(await api.analysis(sessionId, controller.current.signal));
      setError(null);
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
    return () => controller.current?.abort();
  }, [load]);

  const pending = PENDING.includes(analysis?.status);
  useEffect(() => {
    if (!pending) return undefined;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, load]);

  const request = async () => {
    setRequesting(true);
    setError(null);
    try {
      setAnalysis(await api.requestAnalysis(sessionId));
    } catch (err) {
      setError(err.message);
    } finally {
      setRequesting(false);
    }
  };

  if (!analysis && !error) {
    return (
      <div className="stage-loading">
        <span className="proc-spinner" />
      </div>
    );
  }

  return (
    <div className="analysis-view">
      <div className="quiz-head">
        <div>
          <h2>Lecture analysis</h2>
          <p className="script-summary">
            How the lecture comes across, assessed by AI from the transcript: a starting point for reflection, not a
            verdict. Only you can see this.
          </p>
        </div>
      </div>

      {error && (
        <div className="banner error" role="alert">
          <Icon name="alert" size={16} /> <span>{error}</span>
        </div>
      )}

      {analysis?.status === "none" && (
        <StateCard icon="spark" title="No analysis yet">
          <p>This session was processed before lecture analysis existed. It takes about a minute.</p>
          <button className="btn btn-primary" onClick={request} disabled={requesting}>
            {requesting ? <span className="proc-spinner" /> : <Icon name="spark" size={15} />} Analyze lecture
          </button>
        </StateCard>
      )}

      {pending && (
        <StateCard icon={null} title="Analyzing the lecture…" live>
          <p>Scoring content, rhetoric and structure and measuring the time per topic. This can take a few minutes.</p>
        </StateCard>
      )}

      {analysis?.status === "failed" && (
        <StateCard icon="alert" title="The analysis failed" tone="failed">
          <p>{analysis.error_message ?? "Something went wrong while analyzing the lecture."}</p>
          <button className="btn btn-primary" onClick={request} disabled={requesting}>
            <Icon name="refresh" size={15} /> Try again
          </button>
        </StateCard>
      )}

      {analysis?.status === "ready" && <AnalysisResult analysis={analysis} />}
    </div>
  );
}

function StateCard({ icon, title, tone, live = false, children }) {
  return (
    <div className="proc-card analysis-state" aria-live={live ? "polite" : undefined}>
      <div className={"proc-ring" + (tone ? ` ${tone}` : "")}>
        {icon ? <Icon name={icon} size={24} /> : <span className="proc-spinner" />}
      </div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function AnalysisResult({ analysis }) {
  const { scores, topics, metrics } = analysis;
  const axes = CATEGORIES.map((c) => ({ key: c.key, label: c.label, value: scores[c.key].score }));
  const total = topics.reduce((sum, t) => sum + t.duration_seconds, 0);
  const longest = Math.max(...topics.map((t) => t.duration_seconds));
  const tips = CATEGORIES.filter((c) => scores[c.key].tip);

  return (
    <>
      {/* Chart and summary side by side, then the three assessments as equal cards. */}
      <section className="analysis-overview">
        <div className="analysis-radar card">
          <RadarChart axes={axes} max={10} title="Lecture scores" />
        </div>
        <div className="analysis-summary card">
          <dl className="analysis-facts">
            {metrics.words_per_minute != null && (
              <div>
                <dt>Speaking pace</dt>
                <dd>
                  <strong>{metrics.words_per_minute}</strong> words/min
                </dd>
                <dd className="analysis-fact-note">typical for lectures: 110–160</dd>
              </div>
            )}
            <div>
              <dt>Topics</dt>
              <dd>
                <strong>{topics.length}</strong> {topics.length === 1 ? "topic" : "topics"}
              </dd>
              <dd className="analysis-fact-note">over {formatDuration(total)}</dd>
            </div>
          </dl>
          {tips.length > 0 && (
            <div className="analysis-next">
              <h3>Try next time</h3>
              <ul>
                {tips.map((c) => (
                  <li key={c.key}>
                    <Icon name="spark" size={14} />
                    <div>
                      <span className="analysis-next-label">{c.label}</span>
                      <p>{scores[c.key].tip}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      <section className="analysis-cards">
        {CATEGORIES.map((c) => (
          <article className="analysis-card card" key={c.key}>
            <header>
              <div>
                <h3>{c.label}</h3>
                <span className="analysis-card-hint">{c.hint}</span>
              </div>
              <span className="analysis-score" aria-label={`${scores[c.key].score} of 10`}>
                {scores[c.key].score}
                <small>/10</small>
              </span>
            </header>
            <p>{scores[c.key].assessment}</p>
          </article>
        ))}
      </section>

      <section className="analysis-topics card">
        <div className="analysis-section-head">
          <h3>Time per topic</h3>
          <span>{formatDuration(total)} in total</span>
        </div>
        <div className="bar-list">
          {topics.map((t) => (
            <BarRow
              key={t.start_seconds}
              label={
                <>
                  <span className="bar-row-time">{formatTimestamp(t.start_seconds)}</span>
                  {t.title}
                </>
              }
              value={t.duration_seconds}
              max={longest}
              display={`${formatDuration(t.duration_seconds)} · ${percent(t.duration_seconds, total)}%`}
              detail={`${t.title}: from ${formatTimestamp(t.start_seconds)} to ${formatTimestamp(t.end_seconds)}`}
            />
          ))}
        </div>
      </section>

    </>
  );
}
