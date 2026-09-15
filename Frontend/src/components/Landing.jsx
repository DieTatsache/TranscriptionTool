import Icon from "../Icon.jsx";

// Marketing landing page — the friendly entry point before the product demo.
export default function Landing({ onEnter }) {
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
          <a href="#who">Who it's for</a>
          <a href="#pricing">Pricing</a>
          <button className="btn btn-primary btn-sm" onClick={onEnter}>
            Try the demo
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
            <br /> a recap, a quiz, and a video.
          </h1>
          <p>
            Record your session. Sonora listens to the room — not your slides — and turns the actual
            conversation into a short script, an interactive quiz, and a 90-second recap clip your
            participants will actually use.
          </p>
          <div className="lp-hero-cta">
            <button className="btn btn-primary btn-lg" onClick={onEnter}>
              <Icon name="play" size={16} /> Try the interactive demo
            </button>
            <span className="lp-hero-note">No sign-up · takes 30 seconds</span>
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
          <span>Show clients the training worked — and rebook.</span>
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section className="lp-section" id="how">
        <div className="lp-section-head">
          <span className="lp-kicker">How it works</span>
          <h2>Record once. Get three deliverables.</h2>
          <p>The whole flow, from a live session to shareable follow-up material, in minutes.</p>
        </div>
        <div className="lp-steps">
          {[
            { icon: "mic", n: "1", title: "Record the session", body: "Hit record in the room, or upload an existing audio file. Speakers are separated automatically." },
            { icon: "spark", n: "2", title: "Sonora analyzes the audio", body: "It extracts the key points from what was actually said — the reframes, the examples, the answers to real questions." },
            { icon: "script", n: "3", title: "Share the follow-up", body: "A clean recap script, an auto-graded quiz, and a short recap video — all ready to send to participants." },
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
      <section className="lp-section lp-features">
        <div className="lp-feature">
          <div className="lp-feature-text">
            <span className="lp-kicker">The recap script</span>
            <h2>The key points, in the trainer's own words.</h2>
            <p>
              No generic summary. Each point carries the exact quote it came from and a timestamp, so
              participants — and clients — can trust it reflects the real session.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Verbatim quotes with timestamps</li>
              <li><Icon name="check" size={15} /> One-click copy or share</li>
              <li><Icon name="check" size={15} /> Editable before you send</li>
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
              retrieve what they heard instead of letting it fade.
            </p>
            <ul className="lp-checklist">
              <li><Icon name="check" size={15} /> Auto-graded, instant feedback</li>
              <li><Icon name="check" size={15} /> Each answer sourced to a timestamp</li>
              <li><Icon name="check" size={15} /> Pedagogical value, not a gimmick</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <MiniQuiz />
          </div>
        </div>
      </section>

      {/* ---- Who it's for ---- */}
      <section className="lp-section" id="who">
        <div className="lp-section-head">
          <span className="lp-kicker">Who it's for</span>
          <h2>Built for the people who train the room.</h2>
        </div>
        <div className="lp-audience">
          {[
            { title: "Corporate trainers", body: "Prove your training worked, and give clients a reason to rebook." },
            { title: "Solo coaches", body: "Give group sessions a professional follow-up without extra prep." },
            { title: "Adult-ed instructors", body: "VHS, IHK, HWK — turn every session into lasting material." },
            { title: "University lecturers", body: "Individual educators who want their talks to stick." },
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
          <p>Self-serve, no minimum term, cancel anytime. One rebooked training day pays for a year.</p>
        </div>
        <div className="lp-pricing">
          {[
            { name: "Starter", price: "€0", per: "to try", tagline: "See the full flow on a demo session.", features: ["Interactive demo", "1 sample session", "Script + quiz preview"], cta: "Try the demo", primary: false },
            { name: "Trainer", price: "€49", per: "/ month", tagline: "For the working trainer.", features: ["10 sessions / month", "Script, quiz & video", "Shareable participant links", "Client-ready reports"], cta: "Start free trial", primary: true, badge: "Most popular" },
            { name: "Pro", price: "€99", per: "/ month", tagline: "For high-volume schedules.", features: ["Unlimited sessions", "Everything in Trainer", "Custom branding", "Priority rendering"], cta: "Start free trial", primary: false },
          ].map((p) => (
            <div className={"lp-price-card" + (p.primary ? " featured" : "")} key={p.name}>
              {p.badge && <span className="lp-price-badge">{p.badge}</span>}
              <span className="lp-price-name">{p.name}</span>
              <div className="lp-price-amount">
                {p.price}
                <span>{p.per}</span>
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
                onClick={onEnter}
              >
                {p.cta}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="lp-cta">
        <h2>Your last session is already forgotten.</h2>
        <p>The next one doesn't have to be. See what Sonora makes from a real training session.</p>
        <button className="btn btn-primary btn-lg" onClick={onEnter}>
          <Icon name="arrow" size={16} /> Open the demo
        </button>
      </section>

      <footer className="lp-footer">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="wave" size={18} />
          </div>
          <span>Sonora — from what was said</span>
        </div>
        <span className="lp-footer-note">Demo · fictional product · © 2026</span>
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
              <Icon name="wave" size={12} /> "It's a request for more information." <em>00:41</em>
            </div>
          </div>
        </div>
        <div className="hero-chips">
          <span className="hero-chip"><Icon name="script" size={13} /> Script</span>
          <span className="hero-chip"><Icon name="quiz" size={13} /> Quiz</span>
          <span className="hero-chip"><Icon name="video" size={13} /> Video</span>
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
      <div className="mini-src"><Icon name="wave" size={11} /> grounded at 00:41</div>
    </div>
  );
}
