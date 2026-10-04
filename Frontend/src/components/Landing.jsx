import Icon from "../Icon.jsx";
import { formatPrice } from "../format.js";
import { findPlan, isFreePlan, offeredPlans } from "../plans.js";
import { BarRow, RadarChart } from "./charts.jsx";
import { PlansLoading } from "./PlanCards.jsx";

// Marketing landing page — the friendly entry point before the product.
export default function Landing({ onEnter, meta }) {
  const free = findPlan(meta, "free");
  const start = () => (free ? onEnter("register", free.id) : onEnter("register"));
  const startLabel = free ? "Start for free" : "Create your account";

  return (
    <div className="landing">
      {/* ---- Nav ---- */}
      <nav className="lp-nav">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="wave" size={20} />
          </div>
          <div className="brand-text">
            <strong>Sonora</strong>
            <span>from what was said</span>
          </div>
        </div>
        <div className="lp-nav-links">
          <a href="#how">How it works</a>
          <a href="#features">Features</a>
          <a href="#who">Who it&apos;s for</a>
          <a href="#pricing">Pricing</a>
          <button className="btn btn-secondary btn-sm" onClick={() => onEnter("login")}>
            Log in
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => onEnter("register")}>
            Create account
          </button>
        </div>
      </nav>

      {/* ---- Hero ---- */}
      <header className="lp-hero">
        <div className="lp-hero-text fade-up">
          <span className="lp-eyebrow">
            <Icon name="mic" size={13} /> For trainers, coaches & instructors
          </span>
          <h1>
            Turn what you <em>said</em> into
            <br /> a recap, a quiz, and real feedback.
          </h1>
          <p>
            Record your session. Sonora listens to the room — not your slides — and turns the actual
            conversation into a short script and an interactive quiz for your participants, collects their
            feedback, and shows you how the session came across.
          </p>
          <div className="lp-hero-cta">
            <button className="btn btn-primary btn-lg" onClick={start}>
              <Icon name="arrow" size={16} /> {startLabel}
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => onEnter("login")}>
              Log in
            </button>
          </div>
          <div className="lp-trust">
            <Icon name="check" size={14} /> Grounded in real audio, with timestamps you can verify
          </div>
        </div>

        <div className="lp-hero-visual fade-up">
          <HeroCard />
        </div>
      </header>

      {/* ---- Differentiator strip ---- */}
      <section className="lp-strip">
        <div className="lp-strip-item">
          <strong>Not from your slides.</strong>
          <span>From what the room actually heard.</span>
        </div>
        <div className="lp-strip-divider" />
        <div className="lp-strip-item">
          <strong>Every point is sourced.</strong>
          <span>Each recap line links back to a timestamp.</span>
        </div>
        <div className="lp-strip-divider" />
        <div className="lp-strip-item">
          <strong>Proof it landed.</strong>
          <span>Quiz results and feedback show what stuck.</span>
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section className="lp-section" id="how">
        <div className="lp-section-head">
          <span className="lp-kicker">How it works</span>
          <h2>Record once. Share it, and learn from it.</h2>
          <p>From a live session to follow-up material and honest feedback, in minutes.</p>
        </div>
        <div className="lp-steps">
          {[
            { icon: "mic", n: "1", title: "Record the session", body: "Hit record in the room, or upload an existing audio file. Your recording never goes to a third-party AI service." },
            { icon: "spark", n: "2", title: "Sonora works through it", body: "It pulls out the key points from what was actually said — the reframes, the examples, the answers to real questions." },
            { icon: "link", n: "3", title: "Share one link", body: "Script, quiz and a feedback form behind one link or QR code. Participants don't need an account." },
            { icon: "chart", n: "4", title: "See what landed", body: "Quiz results show what stuck, feedback shows how it felt, and the lecture analysis shows what to sharpen next time." },
          ].map((s) => (
            <div className="lp-step-card" key={s.n}>
              <div className="lp-step-icon">
                <Icon name={s.icon} size={20} />
              </div>
              <span className="lp-step-n">Step {s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Feature showcase ---- */}
      <section className="lp-section lp-features" id="features">
        <div className="lp-feature">
          <div className="lp-feature-text">
            <span className="lp-kicker">The recap script</span>
            <h2>The key points, in the trainer&apos;s own words.</h2>
            <p>
              No generic summary. Every takeaway links to the moment it was said, so participants — and
              clients — can trust it reflects the real session.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Takeaways with the timestamp they were said at</li>
              <li><Icon name="check" size={15} /> Summary, overview and open questions</li>
              <li><Icon name="check" size={15} /> Copy it, or share it by link</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <MiniScript />
          </div>
        </div>

        <div className="lp-feature reverse">
          <div className="lp-feature-text">
            <span className="lp-kicker">The quiz</span>
            <h2>Interactive quizzes that fight forgetting.</h2>
            <p>
              Every question is generated from a real moment in the session and shows its source. Participants
              retrieve what they heard instead of letting it fade — and you see which answers they picked.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Auto-graded, instant feedback</li>
              <li><Icon name="check" size={15} /> Each answer explained and sourced to a timestamp</li>
              <li><Icon name="check" size={15} /> Results per question from every listener&apos;s first try</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <MiniQuiz />
          </div>
        </div>

        <div className="lp-feature">
          <div className="lp-feature-text">
            <span className="lp-kicker">Listener feedback</span>
            <h2>Hear from the whole room, not just the loudest voice.</h2>
            <p>
              Every share link can carry a short feedback form: overall rating, clarity, pace and relevance, plus
              one open question. Answers are anonymous, and you see them as soon as they come in.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Anonymous, no account needed</li>
              <li><Icon name="check" size={15} /> One response per listener</li>
              <li><Icon name="check" size={15} /> Shares, averages and every comment</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <MiniFeedback />
          </div>
        </div>

        <div className="lp-feature reverse">
          <div className="lp-feature-text">
            <span className="lp-kicker">Lecture analysis</span>
            <h2>A second opinion on how it came across.</h2>
            <p>
              Content, rhetoric and structure, each scored from 1 to 10 with the reasons and a concrete tip for
              next time — plus how long you spent on each topic and how fast you spoke. Only you see it.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Scores with reasons, not just numbers</li>
              <li><Icon name="check" size={15} /> Time per topic and speaking pace</li>
              <li><Icon name="check" size={15} /> Private to you, never shared</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <MiniAnalysis />
          </div>
        </div>
      </section>

      {/* ---- Who it's for ---- */}
      <section className="lp-section" id="who">
        <div className="lp-section-head">
          <span className="lp-kicker">Who it&apos;s for</span>
          <h2>Built for the people who train the room.</h2>
        </div>
        <div className="lp-audience">
          {[
            { title: "Corporate trainers", body: "Prove your training worked, and give clients a reason to rebook." },
            { title: "Solo coaches", body: "Give group sessions a professional follow-up without extra prep." },
            { title: "Adult-ed instructors", body: "VHS, IHK, HWK — turn every session into lasting material." },
            { title: "University lecturers", body: "See what your students took away, and what to explain again." },
          ].map((a) => (
            <div className="lp-aud-card" key={a.title}>
              <h3>{a.title}</h3>
              <p>{a.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Pricing ---- */}
      <section className="lp-section" id="pricing">
        <div className="lp-section-head">
          <span className="lp-kicker">Pricing</span>
          <h2>Priced against a single rebooking.</h2>
          <p>
            {free
              ? "Start free with one session a month. Upgrade whenever you like — no minimum term, cancel anytime."
              : "Self-serve, no minimum term, cancel anytime. One rebooked training day pays for a year."}
          </p>
        </div>
        {!meta && <PlansLoading />}
        <div className="lp-pricing">
          {offeredPlans(meta).map((p) => (
            <div className={"lp-price-card" + (p.primary ? " featured" : "")} key={p.id}>
              {p.badge && <span className="lp-price-badge">{p.badge}</span>}
              <span className="lp-price-name">{p.name}</span>
              <div className="lp-price-amount">
                {formatPrice(p.monthly_price_cents)}
                <span>/ month</span>
              </div>
              <p className="lp-price-tagline">{p.tagline}</p>
              <ul className="lp-checklist">
                {p.features.map((f) => (
                  <li key={f}>
                    <Icon name="check" size={15} /> {f}
                  </li>
                ))}
              </ul>
              <button
                className={"btn btn-block " + (p.primary ? "btn-primary" : "btn-secondary")}
                onClick={() => onEnter("register", p.id)}
              >
                {isFreePlan(p) ? "Start for free" : `Get ${p.name}`}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="lp-cta">
        <h2>Your last session is already forgotten.</h2>
        <p>The next one doesn&apos;t have to be. Start turning your training sessions into lasting material.</p>
        <div className="lp-cta-btns">
          <button className="btn btn-primary btn-lg" onClick={start}>
            <Icon name="arrow" size={16} /> {startLabel}
          </button>
          <button className="btn btn-ghost btn-lg" onClick={() => onEnter("login")}>
            Log in
          </button>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="wave" size={18} />
          </div>
          <span>Sonora — from what was said</span>
        </div>
        <span className="lp-footer-note">© 2026</span>
      </footer>
    </div>
  );
}

/* ---------- Small visual mocks used on the landing page ---------- */

function HeroCard() {
  return (
    <div className="hero-card">
      <div className="hero-card-bar">
        <span className="hero-dot" /> <span className="hero-dot" /> <span className="hero-dot" />
        <span className="hero-card-title">Handling Objections — Sales Team Q3</span>
      </div>
      <div className="hero-card-body">
        <div className="hero-wave">
          {Array.from({ length: 40 }).map((_, i) => (
            <span key={i} style={{ height: `${20 + Math.abs(Math.sin(i * 0.9)) * 70}%` }} />
          ))}
        </div>
        <div className="hero-point">
          <span className="point-num">1</span>
          <div>
            <strong>An objection is not a rejection</strong>
            <div className="hero-quote">
              <Icon name="wave" size={12} /> &quot;It&apos;s a request for more information.&quot; <em>00:41</em>
            </div>
          </div>
        </div>
        <div className="hero-chips">
          <span className="hero-chip"><Icon name="script" size={13} /> Script</span>
          <span className="hero-chip"><Icon name="quiz" size={13} /> Quiz</span>
          <span className="hero-chip"><Icon name="star" size={13} /> Feedback</span>
          <span className="hero-chip"><Icon name="chart" size={13} /> Analysis</span>
        </div>
      </div>
    </div>
  );
}

function MiniScript() {
  return (
    <div className="mini-card">
      {[
        { n: "1", h: "“Too expensive” is a value problem", at: "01:28" },
        { n: "2", h: "Acknowledge → ask → reframe", at: "02:05" },
        { n: "3", h: "Let silence do the work", at: "04:10" },
      ].map((p) => (
        <div className="mini-point" key={p.n}>
          <span className="point-num">{p.n}</span>
          <div>
            <strong>{p.h}</strong>
            <span className="mini-at"><Icon name="wave" size={11} /> said at {p.at}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function MiniQuiz() {
  return (
    <div className="mini-card">
      <div className="mini-q">An objection is best understood as…</div>
      <div className="mini-opt">A rejection of the offer</div>
      <div className="mini-opt correct">
        A request for more information <Icon name="check" size={14} />
      </div>
      <div className="mini-opt">A negotiation tactic</div>
      <div className="mini-src"><Icon name="wave" size={11} /> grounded at 00:41 · 81% of listeners answered correctly</div>
    </div>
  );
}

function MiniFeedback() {
  return (
    <div className="mini-card">
      <div className="mini-q">How was the pace of the session?</div>
      <div className="bar-list">
        <BarRow label="Too slow" value={2} max={24} display="8%" />
        <BarRow label="Just right" value={19} max={24} display="79%" />
        <BarRow label="Too fast" value={3} max={24} display="13%" />
      </div>
      <p className="mini-comment">“The role-play on price objections was the most useful part.”</p>
      <div className="mini-src"><Icon name="star" size={11} /> 24 anonymous responses · average 4.4 / 5</div>
    </div>
  );
}

const EXAMPLE_SCORES = [
  { key: "content", label: "Content", value: 8 },
  { key: "rhetoric", label: "Rhetoric", value: 7 },
  { key: "structure", label: "Structure", value: 9 },
];

function MiniAnalysis() {
  return (
    <div className="mini-card mini-analysis">
      <RadarChart axes={EXAMPLE_SCORES} max={10} title="Example lecture scores" />
      <p className="mini-tip">
        <Icon name="spark" size={13} /> Next time: name the three steps before the first example.
      </p>
    </div>
  );
}
