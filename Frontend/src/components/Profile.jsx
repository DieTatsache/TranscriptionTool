import { useState } from "react";
import Icon from "../Icon.jsx";
import { DEMO_SESSIONS } from "../data.js";

const MOCK_ACTIVITY = [
  { date: "15. Sep 2026", action: "Session hochgeladen", detail: "Handling Objections — Sales Team Q3" },
  { date: "10. Sep 2026", action: "Quiz geteilt", detail: "4 Fragen · Onboarding Workshop" },
  { date: "3. Sep 2026", action: "Session hochgeladen", detail: "Feedback That Sticks — Leadership" },
  { date: "28. Aug 2026", action: "Profil aktualisiert", detail: "Profilbild geändert" },
];

export default function Profile({ user, onBack, onLogout }) {
  const [activeTab, setActiveTab] = useState("overview");
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({ name: user.name, email: user.email, bio: "Trainer & Coach mit Fokus auf Kommunikation und Leadership.", notifications: true });

  const handleSave = (e) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

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
        {/* Sidebar */}
        <aside className="profile-sidebar">
          <div className="profile-avatar-big">
            <span>{user.initials}</span>
          </div>
          <div className="profile-name">{user.name}</div>
          <div className="profile-email">{user.email}</div>
          <div className="profile-plan-badge">{user.plan} Plan</div>

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

        {/* Content */}
        <main className="profile-content">
          {activeTab === "overview" && (
            <div className="fade-up">
              <h2 className="profile-section-title">Meine Übersicht</h2>

              <div className="profile-stats">
                <div className="stat-card">
                  <div className="stat-value">{DEMO_SESSIONS.length}</div>
                  <div className="stat-label">Sessions gesamt</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">22</div>
                  <div className="stat-label">Quiz-Fragen generiert</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">3h 47m</div>
                  <div className="stat-label">Audio transkribiert</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">6</div>
                  <div className="stat-label">Diesen Monat</div>
                </div>
              </div>

              <h3 className="profile-sub-title">Letzte Aktivität</h3>
              <div className="activity-list">
                {MOCK_ACTIVITY.map((a, i) => (
                  <div className="activity-item" key={i}>
                    <div className="activity-dot" />
                    <div className="activity-body">
                      <div className="activity-action">{a.action}</div>
                      <div className="activity-detail">{a.detail}</div>
                    </div>
                    <div className="activity-date">{a.date}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "settings" && (
            <div className="fade-up">
              <h2 className="profile-section-title">Einstellungen</h2>
              <form className="settings-form" onSubmit={handleSave}>
                <div className="settings-section">
                  <h3 className="settings-section-label">Profil</h3>
                  <div className="field-group">
                    <label className="field-label">Name</label>
                    <input
                      className="field-input"
                      value={form.name}
                      onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    />
                  </div>
                  <div className="field-group">
                    <label className="field-label">E-Mail</label>
                    <input
                      className="field-input"
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                    />
                  </div>
                  <div className="field-group">
                    <label className="field-label">Bio</label>
                    <textarea
                      className="field-input field-textarea"
                      value={form.bio}
                      onChange={(e) => setForm((f) => ({ ...f, bio: e.target.value }))}
                      rows={3}
                    />
                  </div>
                </div>

                <div className="settings-section">
                  <h3 className="settings-section-label">Benachrichtigungen</h3>
                  <label className="toggle-row">
                    <div>
                      <div className="toggle-label">E-Mail-Benachrichtigungen</div>
                      <div className="toggle-sub">Erhalte eine E-Mail, wenn eine Session fertig analysiert wurde.</div>
                    </div>
                    <button
                      type="button"
                      className={"toggle-btn" + (form.notifications ? " on" : "")}
                      onClick={() => setForm((f) => ({ ...f, notifications: !f.notifications }))}
                    >
                      <span className="toggle-thumb" />
                    </button>
                  </label>
                </div>

                <div className="settings-actions">
                  <button type="submit" className="btn btn-primary">
                    {saved ? <><Icon name="check" size={15} /> Gespeichert</> : "Änderungen speichern"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {activeTab === "billing" && (
            <div className="fade-up">
              <h2 className="profile-section-title">Plan & Abrechnung</h2>

              <div className="billing-plan-card">
                <div className="billing-plan-top">
                  <div>
                    <div className="billing-plan-name">Trainer Plan</div>
                    <div className="billing-plan-price">€49 <span>/ Monat</span></div>
                  </div>
                  <span className="plan-badge">Aktiv</span>
                </div>
                <div className="billing-plan-features">
                  {["10 Sessions pro Monat", "Script, Quiz & Video", "Teilnehmer-Links", "Client-Reports"].map((f) => (
                    <div key={f} className="billing-feature">
                      <Icon name="check" size={14} /> {f}
                    </div>
                  ))}
                </div>
                <div className="billing-usage">
                  <div className="billing-usage-label">
                    <span>Sessions diesen Monat</span>
                    <span>{DEMO_SESSIONS.length} / 10</span>
                  </div>
                  <div className="plan-bar">
                    <div className="plan-bar-fill" style={{ width: `${(DEMO_SESSIONS.length / 10) * 100}%` }} />
                  </div>
                </div>
                <div className="billing-actions">
                  <button className="btn btn-secondary btn-sm">Auf Pro upgraden</button>
                  <button className="btn btn-ghost btn-sm">Plan kündigen</button>
                </div>
              </div>

              <h3 className="profile-sub-title">Zahlungsverlauf</h3>
              <div className="billing-history">
                {[
                  { date: "01. Sep 2026", amount: "€49,00", status: "Bezahlt" },
                  { date: "01. Aug 2026", amount: "€49,00", status: "Bezahlt" },
                  { date: "01. Jul 2026", amount: "€49,00", status: "Bezahlt" },
                ].map((r, i) => (
                  <div className="billing-row" key={i}>
                    <span className="billing-row-date">{r.date}</span>
                    <span className="billing-row-desc">Trainer Plan</span>
                    <span className="billing-row-amount">{r.amount}</span>
                    <span className="billing-row-status">{r.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
