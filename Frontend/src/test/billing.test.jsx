import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import App from "../App.jsx";
import Profile from "../components/Profile.jsx";
import Recorder from "../components/Recorder.jsx";
import PlanCards from "../components/PlanCards.jsx";
import { findPlan, isFreePlan, offeredPlans, planAudioMinutes, recordingLimitText, sessionLimitText } from "../plans.js";

const USER = { id: "u1", name: "Ada Lovelace", email: "ada@example.com", bio: "", plan: "none", notify_on_ready: true };
const PLANS = [
  { id: "trainer", name: "Trainer", monthly_price_cents: 4900, monthly_session_limit: 10, max_audio_minutes: null, purchasable: true },
  { id: "pro", name: "Pro", monthly_price_cents: 9900, monthly_session_limit: null, max_audio_minutes: null, purchasable: true },
];
const FREE = { id: "free", name: "Free", monthly_price_cents: 0, monthly_session_limit: 1, max_audio_minutes: 60, purchasable: false };
// META: paid plans only (no free tier); META_FREE: the default, with the free plan first.
const META = { password_min_length: 12, registration_enabled: true, plans: PLANS, languages: [], max_upload_mb: 200, max_audio_minutes: 180 };
const META_FREE = { ...META, plans: [FREE, ...PLANS] };
const NO_PLAN = { id: "none", name: "No plan", monthly_price_cents: 0, monthly_session_limit: 0, purchasable: false };

function usage(plan, used = 0) {
  const remaining = plan.monthly_session_limit == null ? null : Math.max(0, plan.monthly_session_limit - used);
  return { plan, sessions_this_month: used, remaining_this_month: remaining };
}

function payment(overrides) {
  return {
    id: "p1",
    plan: "trainer",
    amount_cents: 4900,
    currency: "EUR",
    status: "succeeded",
    card_brand: "visa",
    card_last4: "4242",
    failure_code: null,
    created_at: "2026-10-04T10:00:00Z",
    ...overrides,
  };
}

function renderBilling(props = {}) {
  return render(
    <Profile
      user={USER}
      meta={META}
      onUserChange={vi.fn()}
      onBack={vi.fn()}
      onLogout={vi.fn()}
      onDeleted={vi.fn()}
      initialTab="billing"
      {...props}
    />,
  );
}

function pay() {
  fireEvent.change(screen.getByLabelText("Cardholder name"), { target: { value: "Ada" } });
  fireEvent.change(screen.getByLabelText("Card number"), { target: { value: "4242424242424242" } });
  fireEvent.change(screen.getByLabelText("Expiry"), { target: { value: "1240" } });
  fireEvent.change(screen.getByLabelText("CVC"), { target: { value: "123" } });
  fireEvent.click(screen.getByRole("button", { name: /^Pay / }));
}

describe("plans", () => {
  it("merge the server's prices and limits with the marketing copy", () => {
    const [free, trainer, pro] = offeredPlans(META_FREE);
    expect(free.features.slice(0, 2)).toEqual(["1 session / month", "Recordings up to 60 min"]);
    expect(isFreePlan(free)).toBe(true);
    expect(trainer.features.slice(0, 2)).toEqual(["10 sessions / month", "Recordings up to 3 hours"]);
    expect(trainer.primary).toBe(true);
    expect(isFreePlan(trainer)).toBe(false);
    expect(pro.features[0]).toBe("Unlimited sessions");
    expect(findPlan(META, "pro").monthly_price_cents).toBe(9900);
    expect(findPlan(META, "platinum")).toBeNull();
    expect(findPlan(META, "free")).toBeNull(); // only offered when the server says so
    expect(sessionLimitText(1)).toBe("1 session / month");
    expect(recordingLimitText(90)).toBe("Recordings up to 90 min");
  });

  it("never allow longer recordings than the server", () => {
    expect(planAudioMinutes(FREE, META)).toBe(60);
    expect(planAudioMinutes(FREE, { ...META, max_audio_minutes: 45 })).toBe(45);
    expect(planAudioMinutes(PLANS[1], META)).toBe(180);
    expect(planAudioMinutes(undefined, null)).toBe(180);
  });

  it("come only from the server: nothing is offered before /meta has loaded", () => {
    expect(offeredPlans(null)).toEqual([]);
    expect(findPlan(null, "trainer")).toBeNull();
    const custom = offeredPlans({ plans: [{ id: "team", name: "Team", monthly_price_cents: 1, monthly_session_limit: 3 }] });
    expect(custom[0]).toMatchObject({ id: "team", tagline: "", features: ["3 sessions / month", "Recordings up to 3 hours"] });
  });

  it("show a loading state instead of prices until the catalog arrives", () => {
    const onPick = vi.fn();
    const { rerender } = render(<PlanCards meta={null} onPick={onPick} />);
    expect(screen.getByRole("status").textContent).toContain("Loading plans");
    expect(screen.queryByText(/€/)).toBeNull();

    rerender(<PlanCards meta={META} onPick={onPick} currentPlan="pro" />);
    expect(screen.getByText("€49")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Current plan" }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Get Trainer" }));
    expect(onPick).toHaveBeenCalledWith("trainer");

    rerender(<PlanCards meta={META_FREE} onPick={onPick} />);
    fireEvent.click(screen.getByRole("button", { name: "Start for free" }));
    expect(onPick).toHaveBeenLastCalledWith("free");
  });
});

describe("Profile billing", () => {
  it("lets accounts without a plan buy one", async () => {
    vi.spyOn(api, "usage").mockResolvedValueOnce(usage(NO_PLAN)).mockResolvedValue(usage(PLANS[0]));
    vi.spyOn(api, "payments").mockResolvedValueOnce([]).mockResolvedValue([payment()]);
    const checkout = vi.spyOn(api, "checkout").mockResolvedValue({ user: { ...USER, plan: "trainer" } });
    const onUserChange = vi.fn();
    renderBilling({ onUserChange });

    expect(await screen.findByText(/have an active plan yet/)).toBeTruthy();
    expect(screen.getByText("No payments yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Get Trainer" }));
    pay();
    fireEvent.click(await screen.findByRole("button", { name: /Go to my account/ }));

    expect(await screen.findByText("Trainer Plan", { selector: ".billing-plan-name" })).toBeTruthy();
    expect(checkout).toHaveBeenCalledWith("trainer", "tok_visa");
    expect(onUserChange).toHaveBeenCalledWith({ ...USER, plan: "trainer" });
    const row = (await screen.findByText("Paid")).closest(".billing-row");
    expect(row.textContent).toContain("Trainer plan · visa •••• 4242");
    expect(row.textContent).toContain("Oct 4, 2026");
    expect(row.textContent).toContain("€49");
  });

  it("cancels a plan after confirmation", async () => {
    vi.spyOn(api, "usage").mockResolvedValueOnce(usage(PLANS[0], 3)).mockResolvedValue(usage(NO_PLAN, 3));
    vi.spyOn(api, "payments").mockResolvedValue([payment(), payment({ id: "p0", status: "failed", failure_code: "card_declined" })]);
    const cancel = vi.spyOn(api, "cancelPlan").mockResolvedValue({ ...USER, plan: "none" });
    renderBilling();

    expect(await screen.findByText("3 / 10")).toBeTruthy();
    expect(screen.getByText("Declined").className).toContain("failed");
    fireEvent.click(screen.getByRole("button", { name: "Cancel plan" }));
    const dialog = screen.getByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel plan" }));

    expect(await screen.findByText(/have an active plan yet/)).toBeTruthy();
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("offers the matching plan change", async () => {
    vi.spyOn(api, "usage").mockResolvedValue(usage(PLANS[1], 12));
    vi.spyOn(api, "payments").mockResolvedValue([]);
    renderBilling();
    expect(await screen.findByText("12 (unlimited)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Switch to Trainer" }));
    expect(screen.getByText("Subscribe to Trainer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Subscribe to Trainer")).toBeNull();
  });

  it("shows cancellation errors", async () => {
    vi.spyOn(api, "usage").mockResolvedValue(usage(PLANS[0]));
    vi.spyOn(api, "payments").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "cancelPlan").mockRejectedValue(Object.assign(new Error("x"), { code: "no_active_plan" }));
    renderBilling();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel plan" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancel plan" }));
    expect((await screen.findByRole("alert")).textContent).toBe("You don't have a plan that can be canceled.");
    expect(screen.getByText("No payments yet.")).toBeTruthy(); // history failed to load
  });

  it("the free plan offers both upgrades but nothing to cancel", async () => {
    vi.spyOn(api, "usage").mockResolvedValue(usage(FREE, 1));
    vi.spyOn(api, "payments").mockResolvedValue([]);
    renderBilling({ meta: META_FREE });
    expect(await screen.findByText("Free Plan", { selector: ".billing-plan-name" })).toBeTruthy();
    expect(screen.getByText("1 / 1")).toBeTruthy();
    expect(screen.getByText("Recordings up to 60 min")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upgrade to Trainer" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upgrade to Pro" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel plan" })).toBeNull();
  });

  it("starts the free plan without the checkout", async () => {
    vi.spyOn(api, "usage").mockResolvedValueOnce(usage(NO_PLAN)).mockResolvedValue(usage(FREE));
    vi.spyOn(api, "payments").mockResolvedValue([]);
    const checkout = vi.spyOn(api, "checkout").mockResolvedValue({ user: { ...USER, plan: "free" }, payment: null });
    const onUserChange = vi.fn();
    renderBilling({ meta: META_FREE, onUserChange });

    fireEvent.click(await screen.findByRole("button", { name: "Start for free" }));

    expect(await screen.findByText("Free Plan", { selector: ".billing-plan-name" })).toBeTruthy();
    expect(checkout).toHaveBeenCalledWith("free"); // no payment token
    expect(screen.queryByText(/Subscribe to/)).toBeNull();
    expect(onUserChange).toHaveBeenCalledWith({ ...USER, plan: "free" });
  });

  it("explains that cancelling returns to the free plan", async () => {
    vi.spyOn(api, "usage").mockResolvedValueOnce(usage(PLANS[0], 2)).mockResolvedValue(usage(FREE, 2));
    vi.spyOn(api, "payments").mockResolvedValue([payment()]);
    vi.spyOn(api, "cancelPlan").mockResolvedValue({ ...USER, plan: "free" });
    renderBilling({ meta: META_FREE });

    fireEvent.click(await screen.findByRole("button", { name: "Cancel plan" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog.textContent).toContain("You're back on the Free plan: one session a month.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel plan" }));

    expect(await screen.findByText("Free Plan", { selector: ".billing-plan-name" })).toBeTruthy();
  });
});

describe("accounts without a plan", () => {
  it("are guided from the sidebar to the checkout", async () => {
    vi.spyOn(api, "meta").mockResolvedValue(META);
    vi.spyOn(api, "me").mockResolvedValue(USER);
    vi.spyOn(api, "listSessions").mockResolvedValue([]);
    vi.spyOn(api, "usage").mockResolvedValue(usage(NO_PLAN));
    vi.spyOn(api, "payments").mockResolvedValue([]);
    render(<App />);

    expect(await screen.findByText("No active plan")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Choose a plan" }));

    expect(await screen.findByText("Plan & billing", { selector: "h2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Get Pro" })).toBeTruthy();
  });

  it("can't start recording and are told why", () => {
    const onChoosePlan = vi.fn();
    render(
      <Recorder meta={META} usage={usage(NO_PLAN)} onUploaded={vi.fn()} onCancel={vi.fn()} onChoosePlan={onChoosePlan} />,
    );
    expect(screen.getByRole("button", { name: /Start recording/ }).disabled).toBe(true);
    expect(screen.getByText("Choose a plan to record and upload sessions.")).toBeTruthy();
    expect(screen.queryByText(/used all sessions/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Choose a plan" }));
    expect(onChoosePlan).toHaveBeenCalled();
  });

  it("see the quota message only when a real plan is used up", () => {
    render(<Recorder meta={META} usage={usage(PLANS[0], 10)} onUploaded={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText("You have used all sessions of your plan this month.")).toBeTruthy();
  });
});
