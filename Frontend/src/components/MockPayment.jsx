import { useState } from "react";
import { createPortal } from "react-dom";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatPrice } from "../format.js";
import { TEST_CARDS, cardProblem, formatCardNumber, formatExpiry, tokenize } from "../mockPaymentProvider.js";

// Simulated checkout. The card form belongs to the (mock) payment provider: card details
// stay in the browser and only its one-time token goes to the API, which charges the
// plan's catalog price.
export default function MockPayment({ plan, onSuccess, onCancel }) {
  const [step, setStep] = useState("form"); // form | processing | success
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);

  const price = formatPrice(plan.monthly_price_cents);

  const submit = async (e) => {
    e.preventDefault();
    const problem = cardProblem({ card, expiry, cvc, name });
    if (problem) {
      setError(problem);
      return;
    }
    const token = tokenize(card);
    // Card data is not kept once it has served its purpose.
    setCard("");
    setCvc("");
    setError(null);
    setStep("processing");
    try {
      const result = await api.checkout(plan.id, token);
      setUser(result.user);
      setStep("success");
    } catch (err) {
      if (err.code === "already_on_plan") {
        onSuccess(null);
        return;
      }
      setStep("form");
      setError(
        err.code === "payment_declined" || err.code === "rate_limited"
          ? err.message
          : "The payment could not be completed. Please try again.",
      );
    }
  };

  if (step === "success") {
    return createPortal(
      <div className="modal-overlay">
        <div className="modal-card payment-card fade-up" role="dialog" aria-modal="true" aria-label="Payment confirmed">
          <div className="payment-success">
            <div className="payment-success-icon">
              <Icon name="check" size={28} />
            </div>
            <h2>Payment confirmed</h2>
            <p>
              Your <strong>{plan.name}</strong> plan is active. Welcome to Sonora!
            </p>
            <button className="btn btn-primary btn-block" onClick={() => onSuccess(user)} autoFocus>
              <Icon name="arrow" size={16} /> Go to my account
            </button>
          </div>
        </div>
      </div>,
      document.body,
    );
  }

  // Portalled: an animated ancestor (transform) would otherwise trap the fixed overlay.
  return createPortal(
    <div className="modal-overlay">
      <div className="modal-card payment-card fade-up" role="dialog" aria-modal="true" aria-labelledby="payment-title">
        <div className="payment-header">
          <div className="payment-plan-badge">
            <span className="payment-plan-name">{plan.name}</span>
            <span className="payment-plan-price">
              {price} <span>/ month</span>
            </span>
          </div>
          <button className="modal-close" onClick={onCancel} aria-label="Close" disabled={step === "processing"}>
            <Icon name="close" size={16} />
          </button>
        </div>

        <h2 className="payment-title" id="payment-title">
          Subscribe to {plan.name}
        </h2>
        <p className="payment-sub">Enter your payment details to activate your plan.</p>

        {step === "processing" ? (
          <div className="payment-processing" aria-live="polite">
            <span className="proc-spinner" />
            <span>Processing payment…</span>
          </div>
        ) : (
          <form className="payment-form" onSubmit={submit} noValidate>
            <div className="field-group">
              <label className="field-label" htmlFor="pay-name">
                Cardholder name
              </label>
              <input
                id="pay-name"
                className="field-input"
                placeholder="Marie Tanner"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="off"
                maxLength={100}
                autoFocus
              />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="pay-card">
                Card number
              </label>
              <div className="field-input-icon">
                {/* autocomplete off: browsers must not offer saved real cards here */}
                <input
                  id="pay-card"
                  className="field-input"
                  placeholder="4242 4242 4242 4242"
                  value={card}
                  onChange={(e) => setCard(formatCardNumber(e.target.value))}
                  autoComplete="off"
                  inputMode="numeric"
                />
                <span className="field-card-icons">
                  <span className="card-brand visa">VISA</span>
                  <span className="card-brand mc">MC</span>
                </span>
              </div>
            </div>

            <div className="payment-row">
              <div className="field-group">
                <label className="field-label" htmlFor="pay-expiry">
                  Expiry
                </label>
                <input
                  id="pay-expiry"
                  className="field-input"
                  placeholder="MM/YY"
                  value={expiry}
                  onChange={(e) => setExpiry(formatExpiry(e.target.value))}
                  autoComplete="off"
                  inputMode="numeric"
                />
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="pay-cvc">
                  CVC
                </label>
                <input
                  id="pay-cvc"
                  className="field-input"
                  placeholder="123"
                  value={cvc}
                  onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))}
                  autoComplete="off"
                  inputMode="numeric"
                />
              </div>
            </div>

            {error && (
              <div className="login-error" role="alert">
                {error}
              </div>
            )}

            <div className="payment-test-cards">
              <span>Simulated checkout — no real charge. Test cards (any future date, any CVC):</span>
              <ul>
                {TEST_CARDS.map((c) => (
                  <li key={c.number}>
                    <button type="button" className="payment-test-card" onClick={() => setCard(formatCardNumber(c.number))}>
                      {formatCardNumber(c.number)}
                    </button>
                    <span>{c.label}</span>
                  </li>
                ))}
              </ul>
            </div>

            <button type="submit" className="btn btn-primary btn-block">
              <Icon name="arrow" size={16} /> Pay {price} and activate
            </button>

            <button type="button" className="btn btn-ghost btn-block payment-skip" onClick={onCancel}>
              Cancel
            </button>
          </form>
        )}
      </div>
    </div>,
    document.body,
  );
}
