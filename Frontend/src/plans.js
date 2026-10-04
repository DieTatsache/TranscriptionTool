// Plans on offer (pricing page, sign-up, profile). Prices and limits come from the server
// (/meta), which also charges them, so the UI can never advertise a different price than it
// bills. The free plan is listed only when the server offers it.

const COPY = {
  free: {
    tagline: "Try it on your next session.",
    features: ["Every feature included", "No payment details needed"],
    primary: false,
  },
  trainer: {
    tagline: "For the working trainer.",
    features: ["Script, quiz & AI chat", "Share links with QR codes", "Listener feedback & lecture analysis"],
    badge: "Most popular",
    primary: true,
  },
  pro: {
    tagline: "For high-volume schedules.",
    features: ["Everything in Trainer"],
    primary: false,
  },
};

export function sessionLimitText(limit) {
  if (limit == null) return "Unlimited sessions";
  return `${limit} ${limit === 1 ? "session" : "sessions"} / month`;
}

// 60 -> "Recordings up to 60 min", 180 -> "Recordings up to 3 hours"
export function recordingLimitText(minutes) {
  const length = minutes >= 120 && minutes % 60 === 0 ? `${minutes / 60} hours` : `${minutes} min`;
  return `Recordings up to ${length}`;
}

// The longest recording of a plan: its own limit, never above the server's.
export function planAudioMinutes(plan, meta) {
  const server = meta?.max_audio_minutes ?? 180;
  return plan?.max_audio_minutes != null ? Math.min(plan.max_audio_minutes, server) : server;
}

// The free plan is switched to without the checkout.
export function isFreePlan(plan) {
  return Boolean(plan) && !plan.purchasable && plan.monthly_price_cents === 0;
}

// Empty until /meta has loaded: the UI never shows a price the server would not charge.
export function offeredPlans(meta) {
  return (meta?.plans ?? []).map((plan) => {
    const copy = COPY[plan.id] ?? { tagline: "", features: [], primary: false };
    const limits = [sessionLimitText(plan.monthly_session_limit), recordingLimitText(planAudioMinutes(plan, meta))];
    return { ...plan, ...copy, features: [...limits, ...copy.features] };
  });
}

export function findPlan(meta, id) {
  return offeredPlans(meta).find((plan) => plan.id === id) ?? null;
}
