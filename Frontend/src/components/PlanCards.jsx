import Icon from "../Icon.jsx";
import { formatPrice } from "../format.js";
import { isFreePlan, offeredPlans } from "../plans.js";

// The plans on offer, with prices and limits from the server (/meta).
export default function PlanCards({ meta, onPick, currentPlan = null }) {
  if (!meta) return <PlansLoading />;
  return (
    <div className="plan-picker-cards">
      {offeredPlans(meta).map((p) => (
        <div key={p.id} className={"plan-picker-card" + (p.primary ? " featured" : "")}>
          {p.badge && <span className="lp-price-badge">{p.badge}</span>}
          <div className="plan-picker-top">
            <span className="plan-picker-name">{p.name}</span>
            <div className="plan-picker-price">
              {formatPrice(p.monthly_price_cents)} <span>/ month</span>
            </div>
          </div>
          <p className="plan-picker-tagline">{p.tagline}</p>
          <ul className="lp-checklist">
            {p.features.map((f) => (
              <li key={f}>
                <Icon name="check" size={14} /> {f}
              </li>
            ))}
          </ul>
          <button
            className={"btn btn-block " + (p.primary ? "btn-primary" : "btn-secondary")}
            onClick={() => onPick(p.id)}
            disabled={p.id === currentPlan}
          >
            {p.id === currentPlan ? "Current plan" : isFreePlan(p) ? "Start for free" : `Get ${p.name}`}
          </button>
        </div>
      ))}
    </div>
  );
}

// Prices are only shown once the server has sent its catalog.
export function PlansLoading() {
  return (
    <div className="plans-loading" role="status">
      <span className="proc-spinner" /> Loading plans…
    </div>
  );
}
