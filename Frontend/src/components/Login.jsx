import { useState } from "react";
import Icon from "../Icon.jsx";

const MOCK_USER = { email: "marie.trainer@example.com", password: "demo1234" };

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    // Simulate network delay
    setTimeout(() => {
      setLoading(false);
      if (email === MOCK_USER.email && password === MOCK_USER.password) {
        onLogin({ name: "Marie Tanner", email, initials: "MT", plan: "Trainer" });
      } else {
        setError("E-Mail oder Passwort ist falsch.");
      }
    }, 800);
  };

  const handleDemoLogin = () => {
    setEmail(MOCK_USER.email);
    setPassword(MOCK_USER.password);
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      onLogin({ name: "Marie Tanner", email: MOCK_USER.email, initials: "MT", plan: "Trainer" });
    }, 600);
  };

  return (
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

        <h1 className="login-title">Willkommen zurück</h1>
        <p className="login-sub">Meld dich an, um deine Sessions zu öffnen.</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="field-group">
            <label className="field-label">E-Mail-Adresse</label>
            <input
              type="email"
              className="field-input"
              placeholder="du@beispiel.de"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="field-group">
            <label className="field-label">Passwort</label>
            <input
              type="password"
              className="field-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button
            type="submit"
            className="btn btn-primary btn-block login-submit"
            disabled={loading}
          >
            {loading ? <span className="proc-spinner" /> : <Icon name="arrow" size={16} />}
            {loading ? "Einen Moment…" : "Anmelden"}
          </button>
        </form>

        <div className="login-divider"><span>oder</span></div>

        <button className="btn btn-secondary btn-block" onClick={handleDemoLogin} disabled={loading}>
          <Icon name="play" size={15} /> Demo-Account nutzen
        </button>

        <p className="login-hint">
          Demo-Zugangsdaten: <code>{MOCK_USER.email}</code> · <code>{MOCK_USER.password}</code>
        </p>
      </div>
    </div>
  );
}
