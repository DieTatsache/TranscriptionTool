import { useCallback, useEffect, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatDate, formatDuration, formatPrice, initials } from "../format.js";
import { useTransient } from "../hooks.js";
import { findPlan, isFreePlan, offeredPlans, planAudioMinutes, recordingLimitText, sessionLimitText } from "../plans.js";
import ConfirmDialog from "./ConfirmDialog.jsx";
import MockPayment from "./MockPayment.jsx";
import PlanCards from "./PlanCards.jsx";

const ACTIVITY_LABELS = {
  account_created: "Account created",
  session_created: "Session uploaded",
  session_deleted: "Session deleted",
  share_created: "Link shared",
  share_revoked: "Link revoked",
  profile_updated: "Profile updated",
  email_changed: "Email address changed",
  password_changed: "Password changed",
  plan_activated: "Plan activated",
  plan_canceled: "Plan canceled",
};

// Included in every plan; the session limit comes from the server's catalog.
const INCLUDED = ["Script, quiz & AI chat", "Participant links & QR codes", "Lecture analysis & feedback"];
const PAYMENT_STATUS = { succeeded: "Paid", failed: "Declined" };

function errorMessage(err, minLength = 12) {
  switch (err.code) {
    case "invalid_password":
      return "The current password is incorrect.";
    case "email_taken":
      return "This email address is already in use.";
    case "weak_password":
      return err.message.includes("differ")
        ? "The new password must be different from the current one."
        : `Please choose a stronger password: at least ${minLength} characters, no common words or patterns.`;
    case "rate_limited":
      return "Too many attempts. Please wait a few minutes.";
    case "no_active_plan":
      return "You don't have a plan that can be canceled.";
    case "plan_not_available":
      return "This plan isn't available.";
    case "validation_error":
      return "Please check your inputs.";
    default:
      return err.message || "Something went wrong.";
  }
}

export default function Profile({ user, meta, onUserChange, onBack, onLogout, onDeleted, initialTab = "overview" }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    api.usage().then(setUsage).catch(() => {});
  }, []);

  return (
    <div className="profile-page">
      <div className="profile-topbar">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          <Icon name="arrow" size={15} style={{ transform: "rotate(180deg)" }} /> Back
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
              { id: "overview", label: "Overview", icon: "script" },
              { id: "settings", label: "Settings", icon: "spark" },
              { id: "billing", label: "Plan & billing", icon: "quiz" },
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
            <div className="profile-nav-divider" />
            <button className="profile-nav-btn profile-nav-logout" onClick={onLogout}>
              Log out
            </button>
          </nav>
        </aside>

        <main className="profile-content">
          {activeTab === "overview" && <Overview />}
          {activeTab === "settings" && (
            <Settings user={user} meta={meta} onUserChange={onUserChange} onDeleted={onDeleted} />
          )}
          {activeTab === "billing" && (
            <Billing meta={meta} usage={usage} onUsageChange={setUsage} onUserChange={onUserChange} />
          )}
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
      <h2 className="profile-section-title">Overview</h2>

      <div className="profile-stats">
        <Stat value={stats.total_sessions} label="Total sessions" />
        <Stat value={stats.quiz_questions} label="Quiz questions generated" />
        <Stat value={stats.audio_seconds ? formatDuration(stats.audio_seconds) : "0"} label="Audio transcribed" />
        <Stat value={stats.sessions_this_month} label="This month" />
      </div>

      <h3 className="profile-sub-title">Recent activity</h3>
      <div className="activity-list">
        {activity.length === 0 && <p className="billing-empty">No activity yet.</p>}
        {activity.map((a, i) => (
          <div className="activity-item" key={i}>
            <div className="activity-dot" />
            <div className="activity-body">
              <div className="activity-action">{ACTIVITY_LABELS[a.type] ?? a.type}</div>
              {a.detail && <div className="activity-detail">{a.detail}</div>}
            </div>
            <div className="activity-date">{formatDate(a.created_at)}</div>
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
      <h2 className="profile-section-title">Settings</h2>
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
  const [saved, showSaved] = useTransient();
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
      showSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="settings-form" onSubmit={save}>
      <div className="settings-section">
        <h3 className="settings-section-label">Profile</h3>
        <div className="field-group">
          <label className="field-label" htmlFor="profile-name">
            Name
          </label>
          <input id="profile-name" className="field-input" value={form.name} onChange={set("name")} maxLength={100} required />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="profile-email">
            Email
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
              Current password (to confirm)
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
            <span className="field-hint">All your other devices will be logged out after the change.</span>
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
        <h3 className="settings-section-label">Notifications</h3>
        <div className="toggle-row">
          <div>
            <div className="toggle-label">Email notifications</div>
            <div className="toggle-sub">Get an email when a session has finished processing.</div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={form.notify_on_ready}
            aria-label="Email notifications"
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
              <Icon name="check" size={15} /> Saved
            </>
          ) : (
            "Save changes"
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
      setError("The new passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(form.current, form.next);
      setForm(empty);
      setMessage("Password changed. All your other devices have been logged out.");
    } catch (err) {
      setError(errorMessage(err, minLength));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="settings-form" onSubmit={submit}>
      <div className="settings-section">
        <h3 className="settings-section-label">Change password</h3>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-current">
            Current password
          </label>
          <input id="pw-current" className="field-input" type="password" value={form.current} onChange={set("current")} autoComplete="current-password" maxLength={128} required />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-new">
            New password
          </label>
          <input id="pw-new" className="field-input" type="password" value={form.next} onChange={set("next")} autoComplete="new-password" minLength={minLength} maxLength={128} required />
          <span className="field-hint">At least {minLength} characters.</span>
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="pw-repeat">
            Repeat new password
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
            Change password
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
      <h3 className="settings-section-label">Delete account</h3>
      <p className="toggle-sub">
        Permanently deletes your account with all sessions, transcripts, quizzes, chats and participant links. This
        cannot be undone.
      </p>
      {!open ? (
        <div>
          <button type="button" className="btn btn-danger btn-sm" onClick={() => setOpen(true)}>
            <Icon name="trash" size={14} /> Delete account…
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="danger-confirm">
          <div className="field-group">
            <label className="field-label" htmlFor="delete-password">
              Confirm with your password
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
              Cancel
            </button>
            <button type="submit" className="btn btn-danger btn-sm" disabled={busy || !password}>
              Delete permanently
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Billing({ meta, usage, onUsageChange, onUserChange }) {
  const [payments, setPayments] = useState(null);
  const [checkoutPlan, setCheckoutPlan] = useState(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const loadPayments = useCallback(() => {
    api
      .payments()
      .then(setPayments)
      .catch(() => setPayments([]));
  }, []);

  useEffect(() => {
    loadPayments();
  }, [loadPayments]);

  if (!usage) return <span className="proc-spinner" />;
  const { plan } = usage;
  const limit = plan.monthly_session_limit;
  const used = usage.sessions_this_month;
  const freeOffered = Boolean(findPlan(meta, "free"));
  // Other plans for sale: upgrades cost more than the current plan, switches less.
  const changes = offeredPlans(meta).filter((p) => p.purchasable && p.id !== plan.id);

  const planChanged = async (updatedUser) => {
    if (updatedUser) onUserChange(updatedUser);
    try {
      onUsageChange(await api.usage());
    } catch {
      // reloaded on the next visit
    }
    loadPayments();
  };

  const choose = async (id) => {
    const chosen = findPlan(meta, id);
    if (!isFreePlan(chosen)) {
      setCheckoutPlan(chosen);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { user: updated } = await api.checkout(chosen.id);
      await planChanged(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.cancelPlan();
      setConfirmCancel(false);
      await planChanged(updated);
    } catch (err) {
      setConfirmCancel(false);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fade-up">
      <h2 className="profile-section-title">Plan & billing</h2>

      {plan.id === "none" ? (
        <div className="billing-noplan">
          <p className="billing-noplan-text">
            You don&apos;t have an active plan yet. Choose a plan to record and upload sessions.
          </p>
          <PlanCards meta={meta} onPick={choose} />
        </div>
      ) : (
        <div className="billing-plan-card">
          <div className="billing-plan-top">
            <div>
              <div className="billing-plan-name">{plan.name} Plan</div>
              <div className="billing-plan-price">
                {formatPrice(plan.monthly_price_cents)} <span>/ month</span>
              </div>
            </div>
            <span className="plan-badge">Active</span>
          </div>
          <div className="billing-plan-features">
            {[sessionLimitText(limit), recordingLimitText(planAudioMinutes(plan, meta)), ...INCLUDED].map((f) => (
              <div key={f} className="billing-feature">
                <Icon name="check" size={14} /> {f}
              </div>
            ))}
          </div>
          <div className="billing-usage">
            <div className="billing-usage-label">
              <span>Sessions this month</span>
              <span>{limit != null ? `${used} / ${limit}` : `${used} (unlimited)`}</span>
            </div>
            {limit != null && (
              <div className="plan-bar">
                <div className="plan-bar-fill" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
              </div>
            )}
          </div>
          <div className="billing-actions">
            {changes.map((p) => (
              <button key={p.id} className="btn btn-secondary btn-sm" onClick={() => setCheckoutPlan(p)}>
                {p.monthly_price_cents > plan.monthly_price_cents ? "Upgrade" : "Switch"} to {p.name}
              </button>
            ))}
            {plan.purchasable && (
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmCancel(true)}>
                Cancel plan
              </button>
            )}
          </div>
          <p className="field-hint">
            Simulated payments: no real money is charged. Plan changes and cancellations take effect
            immediately.
          </p>
        </div>
      )}

      {error && (
        <div className="login-error" role="alert">
          {error}
        </div>
      )}

      <h3 className="profile-sub-title">Payment history</h3>
      <div className="billing-history">
        {payments === null && <span className="proc-spinner" />}
        {payments?.length === 0 && <p className="billing-empty billing-empty-row">No payments yet.</p>}
        {payments?.map((payment) => (
          <div className="billing-row" key={payment.id}>
            <span className="billing-row-date">{formatDate(payment.created_at)}</span>
            <span className="billing-row-desc">
              {findPlan(meta, payment.plan)?.name ?? payment.plan} plan
              {payment.card_last4 && ` · ${payment.card_brand ?? "Card"} •••• ${payment.card_last4}`}
            </span>
            <span className="billing-row-amount">{formatPrice(payment.amount_cents)}</span>
            <span className={"billing-row-status" + (payment.status === "failed" ? " failed" : "")}>
              {PAYMENT_STATUS[payment.status] ?? payment.status}
            </span>
          </div>
        ))}
      </div>

      {checkoutPlan && (
        <MockPayment
          plan={checkoutPlan}
          onSuccess={async (updatedUser) => {
            setCheckoutPlan(null);
            await planChanged(updatedUser);
          }}
          onCancel={() => {
            setCheckoutPlan(null);
            loadPayments(); // declined attempts show up in the history
          }}
        />
      )}
      {confirmCancel && (
        <ConfirmDialog
          title="Cancel plan?"
          confirmLabel="Cancel plan"
          cancelLabel="Keep plan"
          danger
          busy={busy}
          onConfirm={cancel}
          onCancel={() => setConfirmCancel(false)}
        >
          Your {plan.name} plan ends immediately.{" "}
          {freeOffered
            ? "You're back on the Free plan: one session a month."
            : "You can't upload new sessions until you choose a plan again."}{" "}
          Your existing sessions are kept.
        </ConfirmDialog>
      )}
    </div>
  );
}
