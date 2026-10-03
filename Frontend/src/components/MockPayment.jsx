import { useState } from "react";
import Icon from "../Icon.jsx";

const PLANS = {
  trainer: { name: "Trainer", price: "€49", per: "/ month" },
  pro: { name: "Pro", price: "€99", per: "/ month" },
};

function formatCardNumber(val) {
  return val.replace(/\D/g, "").slice(0, 16).replace(/(.{4})/g, "$1 ").trim();
}

function formatExpiry(val) {
  const digits = val.replace(/\D/g, "").slice(0, 4);
  if (digits.length > 2) return digits.slice(0, 2) + "/" + digits.slice(2);
  return digits;
}

export default function MockPayment({ plan, onSuccess, onCancel }) {
  const [step, setStep] = useState("form"); // form | processing | success
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState(null);

  const planInfo = PLANS[plan] ?? PLANS.trainer;

  const submit = (e) => {
    e.preventDefault();
    const rawCard = card.replace(/\s/g, "");
    if (rawCard.length < 16) { setError("Please enter a valid 16-digit card number."); return; }
    const [mm, yy] = expiry.split("/");
    if (!mm || !yy || mm > 12 || mm < 1) { setError("Please enter a valid expiry date."); return; }
    if (cvc.replace(/\D/g, "").length < 3) { setError("Please enter a valid CVC."); return; }
    if (!name.trim()) { setError("Please enter the cardholder name."); return; }

    setError(null);
    setStep("processing");
    setTimeout(() => setStep("success"), 2200);
  };

  if (step === "success") {
    return (
      <div className="modal-overlay" onClick={onSuccess}>
        <div className="modal-card payment-card fade-up" onClick={(e) => e.stopPropagation()}>
          <div className="payment-success">
            <div className="payment-success-icon">
              <Icon name="check" size={28} />
            </div>
            <h2>Payment confirmed</h2>
            <p>
              Your <strong>{planInfo.name}</strong> subscription is active. Welcome to Sonora!
            </p>
            <button className="btn btn-primary btn-block" onClick={onSuccess}>
              <Icon name="arrow" size={16} /> Go to my account
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card payment-card fade-up">
        <div className="payment-header">
          <div className="payment-plan-badge">
            <span className="payment-plan-name">{planInfo.name}</span>
            <span className="payment-plan-price">{planInfo.price} <span>{planInfo.per}</span></span>
          </div>
          <button className="modal-close" onClick={onCancel} aria-label="Cancel">
            <Icon name="close" size={16} />
          </button>
        </div>

        <h2 className="payment-title">Subscribe to {planInfo.name}</h2>
        <p className="payment-sub">Enter your payment details to activate your plan.</p>

        {step === "processing" ? (
          <div className="payment-processing">
            <span className="proc-spinner" />
            <span>Processing payment…</span>
          </div>
        ) : (
          <form className="payment-form" onSubmit={submit}>
            <div className="field-group">
              <label className="field-label" htmlFor="pay-name">Cardholder name</label>
              <input
                id="pay-name"
                className="field-input"
                placeholder="Marie Tanner"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="cc-name"
                required
                autoFocus
              />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="pay-card">Card number</label>
              <div className="field-input-icon">
                <input
                  id="pay-card"
                  className="field-input"
                  placeholder="1234 5678 9012 3456"
                  value={card}
                  onChange={(e) => setCard(formatCardNumber(e.target.value))}
                  autoComplete="cc-number"
                  inputMode="numeric"
                  required
                />
                <span className="field-card-icons">
                  <span className="card-brand visa">VISA</span>
                  <span className="card-brand mc">MC</span>
                </span>
              </div>
            </div>

            <div className="payment-row">
              <div className="field-group">
                <label className="field-label" htmlFor="pay-expiry">Expiry</label>
                <input
                  id="pay-expiry"
                  className="field-input"
                  placeholder="MM/YY"
                  value={expiry}
                  onChange={(e) => setExpiry(formatExpiry(e.target.value))}
                  autoComplete="cc-exp"
                  inputMode="numeric"
                  required
                />
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="pay-cvc">CVC</label>
                <input
                  id="pay-cvc"
                  className="field-input"
                  placeholder="123"
                  value={cvc}
                  onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))}
                  autoComplete="cc-csc"
                  inputMode="numeric"
                  required
                />
              </div>
            </div>

            {error && (
              <div className="login-error" role="alert">{error}</div>
            )}

            <div className="payment-secure">
              <Icon name="check" size={13} /> Simulated checkout — no real charge will be made
            </div>

            <button type="submit" className="btn btn-primary btn-block">
              <Icon name="arrow" size={16} /> Pay {planInfo.price} and activate
            </button>

            <button type="button" className="btn btn-ghost btn-block payment-skip" onClick={onCancel}>
              Cancel
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
