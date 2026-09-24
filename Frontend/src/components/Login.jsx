import { useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { DEMO_LOGIN } from "../features.js";

// German messages for the API error codes this screen can receive.
function errorMessage(err, minLength) {
  switch (err.code) {
    case "invalid_credentials":
      return "E-Mail oder Passwort ist falsch.";
    case "login_locked":
      return "Zu viele fehlgeschlagene Anmeldeversuche. Bitte warte ein paar Minuten.";
    case "rate_limited":
      return "Zu viele Anfragen. Bitte versuche es gleich noch einmal.";
    case "email_taken":
      return "Für diese E-Mail-Adresse gibt es bereits ein Konto.";
    case "weak_password":
      return `Bitte wähle ein sichereres Passwort: mindestens ${minLength} Zeichen, keine gängigen Wörter, Muster oder Teile deiner E-Mail-Adresse.`;
    case "registration_disabled":
      return "Die Registrierung ist derzeit geschlossen.";
    case "validation_error":
      return "Bitte überprüfe deine Eingaben.";
    case "network_error":
      return "Der Server ist nicht erreichbar. Bitte prüfe deine Verbindung.";
    default:
      return "Etwas ist schiefgelaufen. Bitte versuche es erneut.";
  }
}

export default function Login({ mode, onModeChange, meta, notice, onLogin }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const registering = mode === "register";
  const minLength = meta?.password_min_length ?? 12;
  const canRegister = meta?.registration_enabled ?? true;

  const submit = async (credentials) => {
    setError(null);
    setLoading(true);
    try {
      const user = registering
        ? await api.register(name, credentials.email, credentials.password)
        : await api.login(credentials.email, credentials.password);
      onLogin(user);
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

        <h1 className="login-title">{registering ? "Konto erstellen" : "Willkommen zurück"}</h1>
        <p className="login-sub">
          {registering
            ? "Erstelle dein Trainer-Konto und nimm deine erste Session auf."
            : "Meld dich an, um deine Sessions zu öffnen."}
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
              E-Mail-Adresse
            </label>
            <input
              id="email"
              type="email"
              className="field-input"
              placeholder="du@beispiel.de"
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
              Passwort
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
                Mindestens {minLength} Zeichen. Tipp: ein Satz aus mehreren Wörtern ist sicher und gut zu merken.
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
            {loading ? "Einen Moment…" : registering ? "Konto erstellen" : "Anmelden"}
          </button>
        </form>

        {canRegister && (
          <p className="login-switch">
            {registering ? "Schon registriert?" : "Noch kein Konto?"}{" "}
            <button type="button" onClick={() => switchMode(registering ? "login" : "register")}>
              {registering ? "Anmelden" : "Kostenlos registrieren"}
            </button>
          </p>
        )}

        {DEMO_LOGIN && !registering && (
          <>
            <div className="login-divider">
              <span>oder</span>
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
              <Icon name="play" size={15} /> Demo-Account nutzen
            </button>
            <p className="login-hint">
              Lokale Entwicklung: <code>{DEMO_LOGIN.email}</code> (angelegt mit <code>seed-demo</code>)
            </p>
          </>
        )}
      </div>
    </div>
  );
}
