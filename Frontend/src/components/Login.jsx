import { useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { DEMO_LOGIN } from "../features.js";
import MockPayment from "./MockPayment.jsx";

// Error messages for the API error codes
function errorMessage(err, minLength) {
  switch (err.code) {
    case "invalid_credentials":
      return "Email or password is incorrect.";
    case "login_locked":
      return "Too many failed attempts. Please wait a few minutes and try again.";
    case "rate_limited":
      return "Too many requests. Please try again shortly.";
    case "email_taken":
      return "An account with this email address already exists.";
    case "weak_password":
      return `Please choose a stronger password: at least ${minLength} characters, no common words, patterns, or parts of your email.`;
    case "registration_disabled":
      return "Registration is currently closed.";
    case "validation_error":
      return "Please check your inputs.";
    case "network_error":
      return "The server is unreachable. Please check your connection.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export default function Login({ mode, onModeChange, meta, notice, onLogin, plan: initialPlan }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pendingUser, setPendingUser] = useState(null);
  const [selectedPlan, setSelectedPlan] = useState(initialPlan ?? null);

  const registering = mode === "register";
  const minLength = meta?.password_min_length ?? 12;
  const canRegister = meta?.registration_enabled ?? true;

  // picking plan
  if (registering && !selectedPlan) {
    return <PlanPicker onPick={setSelectedPlan} onBack={() => onModeChange("login")} />;
  }

  const submit = async (credentials) => {
    setError(null);
    setLoading(true);
    try {
      const user = mode === "register"
        ? await api.register(name, credentials.email, credentials.password, selectedPlan)
        : await api.login(credentials.email, credentials.password);
      if (mode === "register" && (selectedPlan === "trainer" || selectedPlan === "pro")) {
        setPendingUser({ user, plan: selectedPlan });
      } else {
        onLogin(user);
      }
    } catch (err) {
      setError(errorMessage(err, minLength));
      setLoading(false);
    }
  };

  const switchMode = (next) => {
    setError(null);
    onModeChange(next);
  };

  return (
    <>
      {pendingUser && (
        <MockPayment
          plan={pendingUser.plan}
          onSuccess={() => onLogin(pendingUser.user)}
          onCancel={() => { setPendingUser(null); setLoading(false); }}
        />
      )}
    <div className="login-page">
      <div className="login-card fade-up">
        <div className="login-brand">
          <div className="brand-mark">
            <Icon name="wave" size={22} />
          </div>
          <div className="brand-text">
            <strong>Sonora</strong>
            <span>from what was said</span>
          </div>
        </div>

        <h1 className="login-title">{registering ? "Create your account" : "Welcome back"}</h1>
        <p className="login-sub">
          {registering
            ? "Set up your trainer account and start your first session."
            : "Log in to open your sessions."}
        </p>

        {notice && <div className="login-notice">{notice}</div>}

        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit({ email, password });
          }}
        >
          {registering && (
            <div className="field-group">
              <label className="field-label" htmlFor="name">
                Name
              </label>
              <input
                id="name"
                className="field-input"
                placeholder="Marie Tanner"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                maxLength={100}
                required
                autoFocus
              />
            </div>
          )}

          <div className="field-group">
            <label className="field-label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              className="field-input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete={registering ? "email" : "username"}
              maxLength={254}
              required
              autoFocus={!registering}
            />
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="field-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={registering ? "new-password" : "current-password"}
              minLength={registering ? minLength : undefined}
              maxLength={128}
              required
            />
            {registering && (
              <span className="field-hint">
                At least {minLength} characters. Tip: a short phrase is secure and easy to remember.
              </span>
            )}
          </div>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-primary btn-block login-submit" disabled={loading}>
            {loading ? <span className="proc-spinner" /> : <Icon name="arrow" size={16} />}
            {loading ? "One moment…" : registering ? "Create account" : "Log in"}
          </button>
        </form>

        {canRegister && (
          <p className="login-switch">
            {registering ? "Already have an account?" : "Don't have an account?"}{" "}
            <button type="button" onClick={() => switchMode(registering ? "login" : "register")}>
              {registering ? "Log in" : "Create one for free"}
            </button>
          </p>
        )}

        {DEMO_LOGIN && !registering && (
          <>
            <div className="login-divider">
              <span>or</span>
            </div>
            <button
              className="btn btn-secondary btn-block"
              onClick={() => {
                setEmail(DEMO_LOGIN.email);
                setPassword(DEMO_LOGIN.password);
                submit(DEMO_LOGIN);
              }}
              disabled={loading}
            >
              <Icon name="play" size={15} /> Use demo account
            </button>
            <p className="login-hint">
              Local dev: <code>{DEMO_LOGIN.email}</code> (created with <code>seed-demo</code>)
            </p>
          </>
        )}
      </div>
    </div>
    </>
  );
}

const PLAN_OPTIONS = [
  {
    id: "trainer",
    name: "Trainer",
    price: "€49",
    per: "/ month",
    tagline: "For the working trainer.",
    features: ["10 sessions / month", "Script, quiz & video", "Shareable participant links", "Client-ready reports"],
    primary: true,
    badge: "Most popular",
  },
  {
    id: "pro",
    name: "Pro",
    price: "€99",
    per: "/ month",
    tagline: "For high-volume schedules.",
    features: ["Unlimited sessions", "Everything in Trainer", "Custom branding", "Priority rendering"],
    primary: false,
  },
];

function PlanPicker({ onPick, onBack }) {
  return (
    <div className="login-page plan-picker-page">
      <div className="plan-picker fade-up">
        <div className="login-brand">
          <div className="brand-mark">
            <Icon name="wave" size={22} />
          </div>
          <div className="brand-text">
            <strong>Sonora</strong>
            <span>from what was said</span>
          </div>
        </div>

        <h1 className="login-title">Choose your plan</h1>
        <p className="login-sub">Pick the plan that fits your schedule. You can change it anytime.</p>

        <div className="plan-picker-cards">
          {PLAN_OPTIONS.map((p) => (
            <div key={p.id} className={"plan-picker-card" + (p.primary ? " featured" : "")}>
              {p.badge && <span className="lp-price-badge">{p.badge}</span>}
              <div className="plan-picker-top">
                <span className="plan-picker-name">{p.name}</span>
                <div className="plan-picker-price">
                  {p.price} <span>{p.per}</span>
                </div>
              </div>
              <p className="plan-picker-tagline">{p.tagline}</p>
              <ul className="lp-checklist">
                {p.features.map((f) => (
                  <li key={f}><Icon name="check" size={14} /> {f}</li>
                ))}
              </ul>
              <button
                className={"btn btn-block " + (p.primary ? "btn-primary" : "btn-secondary")}
                onClick={() => onPick(p.id)}
              >
                Get {p.name}
              </button>
            </div>
          ))}
        </div>

        <p className="login-switch">
          Already have an account?{" "}
          <button type="button" onClick={onBack}>Log in</button>
        </p>
      </div>
    </div>
  );
}
