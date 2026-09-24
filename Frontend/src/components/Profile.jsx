import { useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatDate, formatDuration, formatPrice, initials } from "../format.js";

const ACTIVITY_LABELS = {
  account_created: "Konto erstellt",
  session_created: "Session hochgeladen",
  session_deleted: "Session gelöscht",
  share_created: "Link geteilt",
  share_revoked: "Link widerrufen",
  profile_updated: "Profil aktualisiert",
  email_changed: "E-Mail-Adresse geändert",
  password_changed: "Passwort geändert",
};

const PLAN_FEATURES = {
  starter: ["1 Session pro Monat", "Script, Quiz & KI-Chat", "Teilnehmer-Links"],
  trainer: ["10 Sessions pro Monat", "Script, Quiz & KI-Chat", "Teilnehmer-Links"],
  pro: ["Unbegrenzte Sessions", "Script, Quiz & KI-Chat", "Teilnehmer-Links"],
};

function errorMessage(err, minLength = 12) {
  switch (err.code) {
    case "invalid_password":
      return "Das aktuelle Passwort ist falsch.";
    case "email_taken":
      return "Diese E-Mail-Adresse wird bereits verwendet.";
    case "weak_password":
      return err.message.includes("differ")
        ? "Das neue Passwort muss sich vom aktuellen unterscheiden."
        : `Bitte wähle ein sichereres Passwort: mindestens ${minLength} Zeichen, keine gängigen Wörter oder Muster.`;
    case "rate_limited":
      return "Zu viele Versuche. Bitte warte ein paar Minuten.";
    case "validation_error":
      return "Bitte überprüfe deine Eingaben.";
    default:
      return err.message || "Etwas ist schiefgelaufen.";
  }
}

export default function Profile({ user, meta, onUserChange, onBack, onLogout, onDeleted }) {
  const [activeTab, setActiveTab] = useState("overview");
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    api.usage().then(setUsage).catch(() => {});
  }, []);

  return (
    <div className="profile-page">
      <div className="profile-topbar">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          <Icon name="arrow" size={15} style={{ transform: "rotate(180deg)" }} /> Zurück
        </button>
        <button className="btn btn-ghost btn-sm logout-btn" onClick={onLogout}>
          Abmelden
        </button>
      </div>

      <div className="profile-layout">
        <aside className="profile-sidebar">
          <div className="profile-avatar-big">
            <span>{initials(user.name)}</span>
          </div>
          <div className="profile-name">{user.name}</div>
          <div className="profile-email">{user.email}</div>
          <div className="profile-plan-badge">{usage?.plan.name ?? user.plan} Plan</div>

          <nav className="profile-nav">
            {[
              { id: "overview", label: "Übersicht", icon: "script" },
              { id: "settings", label: "Einstellungen", icon: "spark" },
              { id: "billing", label: "Plan & Abrechnung", icon: "quiz" },
            ].map((t) => (
              <button
                key={t.id}
                className={"profile-nav-btn" + (activeTab === t.id ? " active" : "")}
                onClick={() => setActiveTab(t.id)}
              >
                <Icon name={t.icon} size={15} />
                {t.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="profile-content">
          {activeTab === "overview" && <Overview />}
          {activeTab === "settings" && (
            <Settings user={user} meta={meta} onUserChange={onUserChange} onDeleted={onDeleted} />
          )}
          {activeTab === "billing" && <Billing usage={usage} />}
        </main>
      </div>
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api.stats(), api.activity(10)])
      .then(([s, a]) => {
        setStats(s);
        setActivity(a);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="login-error">{error}</div>;
  if (!stats) return <span className="proc-spinner" />;

  return (
    <div className="fade-up">
      <h2 className="profile-section-title">Meine Übersicht</h2>

      <div className="profile-stats">
        <Stat value={stats.total_sessions} label="Sessions gesamt" />
        <Stat value={stats.quiz_questions} label="Quiz-Fragen generiert" />
        <Stat value={stats.audio_seconds ? formatDuration(stats.audio_seconds) : "0"} label="Audio transkribiert" />
        <Stat value={stats.sessions_this_month} label="Diesen Monat" />
      </div>

      <h3 className="profile-sub-title">Letzte Aktivität</h3>
      <div className="activity-list">
        {activity.length === 0 && <p className="billing-empty">Noch keine Aktivität.</p>}
        {activity.map((a, i) => (
          <div className="activity-item" key={i}>
            <div className="activity-dot" />
            <div className="activity-body">
              <div className="activity-action">{ACTIVITY_LABELS[a.type] ?? a.type}</div>
              {a.detail && <div className="activity-detail">{a.detail}</div>}
            </div>
            <div className="activity-date">{formatDate(a.created_at, "de-DE")}</div>
          </div>
        ))}
      </div>
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

function Settings({ user, meta, onUserChange, onDeleted }) {
  const minLength = meta?.password_min_length ?? 12;
  return (
    <div className="fade-up">
      <h2 className="profile-section-title">Einstellungen</h2>
      <ProfileForm user={user} onUserChange={onUserChange} />
      <PasswordForm minLength={minLength} />
      <DeleteAccount onDeleted={onDeleted} />
    </div>
  );
}

function ProfileForm({ user, onUserChange }) {
  const [form, setForm] = useState({
    name: user.name,
    email: user.email,
    bio: user.bio,
    notify_on_ready: user.notify_on_ready,
    current_password: "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const emailChanged = form.email.trim().toLowerCase() !== user.email;
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const changes = { name: form.name, bio: form.bio, notify_on_ready: form.notify_on_ready };
      if (emailChanged) {
        changes.email = form.email;
        changes.current_password = form.current_password;
      }
      const updated = await api.updateProfile(changes);
      onUserChange(updated);
      setForm((f) => ({ ...f, email: updated.email, current_password: "" }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="settings-form" onSubmit={save}>
      <div className="settings-section">
        <h3 className="settings-section-label">Profil</h3>
        <div className="field-group">
          <label className="field-label" htmlFor="profile-name">
            Name
          </label>
          <input id="profile-name" className="field-input" value={form.name} onChange={set("name")} maxLength={100} required />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="profile-email">
            E-Mail
          </label>
          <input
            id="profile-email"
            className="field-input"
            type="email"
            value={form.email}
            onChange={set("email")}
            autoComplete="email"
            maxLength={254}
            required
          />
        </div>
        {emailChanged && (
          <div className="field-group">
            <label className="field-label" htmlFor="profile-current-password">
              Aktuelles Passwort (zur Bestätigung)
            </label>
            <input
              id="profile-current-password"
              className="field-input"
              type="password"
              value={form.current_password}
              onChange={set("current_password")}
              autoComplete="current-password"
              maxLength={128}
              required
            />
            <span className="field-hint">Nach der Änderung werden alle anderen Geräte abgemeldet.</span>
          </div>
        )}
        <div className="field-group">
          <label className="field-label" htmlFor="profile-bio">
            Bio
          </label>
          <textarea
            id="profile-bio"
            className="field-input field-textarea"
            value={form.bio}
            onChange={set("bio")}
            maxLength={1000}
            rows={3}
          />
        </div>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-label">Benachrichtigungen</h3>
        <div className="toggle-row">
          <div>
            <div className="toggle-label">E-Mail-Benachrichtigungen</div>
            <div className="toggle-sub">Erhalte eine E-Mail, wenn eine Session fertig analysiert wurde.</div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={form.notify_on_ready}
            aria-label="E-Mail-Benachrichtigungen"
            className={"toggle-btn" + (form.notify_on_ready ? " on" : "")}
            onClick={() => setForm((f) => ({ ...f, notify_on_ready: !f.notify_on_ready }))}
          >
            <span className="toggle-thumb" />
          </button>
        </div>
      </div>

      {error && (
        <div className="login-error" role="alert">
          {error}
        </div>
      )}
      <div className="settings-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saved ? (
            <>
              <Icon name="check" size={15} /> Gespeichert
            </>
          ) : (
            "Änderungen speichern"
          )}
        </button>
      </div>
    </form>
  );
}

function PasswordForm({ minLength }) {
  const empty = { current: "", next: "", repeat: "" };
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (form.next !== form.repeat) {
      setError("Die neuen Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(form.current, form.next);
      setForm(empty);
      setMessage("Passwort geändert. Alle anderen Geräte wurden abgemeldet.");
    } catch (err) {
      setError(errorMessage(err, minLength));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-section">
        <h3 className="settings-section-label">Passwort ändern</h3>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-current">
            Aktuelles Passwort
          </label>
          <input id="pw-current" className="field-input" type="password" value={form.current} onChange={set("current")} autoComplete="current-password" maxLength={128} required />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-new">
            Neues Passwort
          </label>
          <input id="pw-new" className="field-input" type="password" value={form.next} onChange={set("next")} autoComplete="new-password" minLength={minLength} maxLength={128} required />
          <span className="field-hint">Mindestens {minLength} Zeichen.</span>
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-repeat">
            Neues Passwort wiederholen
          </label>
          <input id="pw-repeat" className="field-input" type="password" value={form.repeat} onChange={set("repeat")} autoComplete="new-password" maxLength={128} required />
        </div>
        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}
        {message && <div className="login-notice">{message}</div>}
        <div className="settings-actions">
          <button type="submit" className="btn btn-secondary" disabled={busy}>
            Passwort ändern
          </button>
        </div>
      </div>
    </form>
  );
}

function DeleteAccount({ onDeleted }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password);
      onDeleted();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="settings-section danger-zone">
      <h3 className="settings-section-label">Konto löschen</h3>
      <p className="toggle-sub">
        Löscht dein Konto mit allen Sessions, Transkripten, Quizzen, Chats und Teilnehmer-Links endgültig. Dies kann
        nicht rückgängig gemacht werden.
      </p>
      {!open ? (
        <div>
          <button type="button" className="btn btn-danger btn-sm" onClick={() => setOpen(true)}>
            <Icon name="trash" size={14} /> Konto löschen…
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="danger-confirm">
          <div className="field-group">
            <label className="field-label" htmlFor="delete-password">
              Passwort zur Bestätigung
            </label>
            <input
              id="delete-password"
              className="field-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              maxLength={128}
              required
              autoFocus
            />
          </div>
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}
          <div className="modal-actions">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)} disabled={busy}>
              Abbrechen
            </button>
            <button type="submit" className="btn btn-danger btn-sm" disabled={busy || !password}>
              Endgültig löschen
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Billing({ usage }) {
  if (!usage) return <span className="proc-spinner" />;
  const { plan } = usage;
  const limit = plan.monthly_session_limit;
  const used = usage.sessions_this_month;

  return (
    <div className="fade-up">
      <h2 className="profile-section-title">Plan & Abrechnung</h2>

      <div className="billing-plan-card">
        <div className="billing-plan-top">
          <div>
            <div className="billing-plan-name">{plan.name} Plan</div>
            <div className="billing-plan-price">
              {formatPrice(plan.monthly_price_cents)} <span>/ Monat</span>
            </div>
          </div>
          <span className="plan-badge">Aktiv</span>
        </div>
        <div className="billing-plan-features">
          {(PLAN_FEATURES[plan.id] ?? []).map((f) => (
            <div key={f} className="billing-feature">
              <Icon name="check" size={14} /> {f}
            </div>
          ))}
        </div>
        <div className="billing-usage">
          <div className="billing-usage-label">
            <span>Sessions diesen Monat</span>
            <span>{limit != null ? `${used} / ${limit}` : `${used} (unbegrenzt)`}</span>
          </div>
          {limit != null && (
            <div className="plan-bar">
              <div className="plan-bar-fill" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
            </div>
          )}
        </div>
        <div className="billing-actions">
          <button className="btn btn-secondary btn-sm" disabled title="Online-Abrechnung folgt in Kürze">
            Auf Pro upgraden
          </button>
          <button className="btn btn-ghost btn-sm" disabled title="Online-Abrechnung folgt in Kürze">
            Plan kündigen
          </button>
        </div>
        <p className="field-hint">Online-Zahlung und Planwechsel werden in Kürze freigeschaltet.</p>
      </div>

      <h3 className="profile-sub-title">Zahlungsverlauf</h3>
      <div className="billing-history">
        <p className="billing-empty">Noch keine Zahlungen.</p>
      </div>
    </div>
  );
}
