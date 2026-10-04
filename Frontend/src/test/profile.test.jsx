import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import Profile from "../components/Profile.jsx";

const USER = { id: "u1", name: "Ada Lovelace", email: "ada@example.com", bio: "Teacher", plan: "trainer", notify_on_ready: true };
const USAGE = {
  plan: { id: "trainer", name: "Trainer", monthly_price_cents: 4900, monthly_session_limit: 10, purchasable: true },
  sessions_this_month: 1,
  remaining_this_month: 9,
};

function renderProfile(props = {}) {
  vi.spyOn(api, "usage").mockResolvedValue(USAGE);
  const handlers = { onUserChange: vi.fn(), onBack: vi.fn(), onLogout: vi.fn(), onDeleted: vi.fn() };
  render(<Profile user={USER} meta={{ password_min_length: 12 }} {...handlers} {...props} />);
  return handlers;
}

function fill(label, value) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("Profile overview", () => {
  it("shows totals and the activity log, including plan changes", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({ total_sessions: 3, quiz_questions: 12, audio_seconds: 3700, sessions_this_month: 1 });
    vi.spyOn(api, "activity").mockResolvedValue([
      { type: "plan_activated", detail: "Trainer", created_at: "2026-10-04T10:00:00Z" },
      { type: "plan_canceled", detail: "Pro", created_at: "2026-10-03T10:00:00Z" },
      { type: "something_new", detail: "", created_at: "2026-10-02T10:00:00Z" },
    ]);
    const { onBack } = renderProfile();

    expect(await screen.findByText("Plan activated")).toBeTruthy();
    expect(screen.getByText("Plan canceled")).toBeTruthy();
    expect(screen.getByText("something_new")).toBeTruthy(); // unknown types are shown as they are
    expect(screen.getByText("1h 01m")).toBeTruthy();
    expect(await screen.findByText("Trainer Plan")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Back/ }));
    expect(onBack).toHaveBeenCalled();
  });

  it("reports load errors", async () => {
    vi.spyOn(api, "stats").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "activity").mockResolvedValue([]);
    renderProfile();
    expect(await screen.findByText("offline")).toBeTruthy();
  });
});

describe("Profile settings", () => {
  it("saves profile changes", async () => {
    const update = vi.spyOn(api, "updateProfile").mockResolvedValue({ ...USER, name: "Ada King", notify_on_ready: false });
    const { onUserChange } = renderProfile({ initialTab: "settings" });

    fill("Name", "Ada King");
    fireEvent.click(screen.getByRole("switch", { name: "Email notifications" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Saved")).toBeTruthy();
    expect(update).toHaveBeenCalledWith({ name: "Ada King", bio: "Teacher", notify_on_ready: false });
    expect(onUserChange).toHaveBeenCalledWith({ ...USER, name: "Ada King", notify_on_ready: false });
  });

  it("asks for the password when the email changes", async () => {
    const update = vi
      .spyOn(api, "updateProfile")
      .mockRejectedValueOnce(Object.assign(new Error("x"), { code: "invalid_password" }))
      .mockRejectedValueOnce(Object.assign(new Error("x"), { code: "email_taken" }));
    renderProfile({ initialTab: "settings" });

    fill("Email", "new@example.com");
    fill("Current password (to confirm)", "secret-password");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The current password is incorrect.");
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ email: "new@example.com", current_password: "secret-password" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This email address is already in use.");
  });

  it("changes the password and rejects mismatches locally", async () => {
    const change = vi
      .spyOn(api, "changePassword")
      .mockRejectedValueOnce(Object.assign(new Error("must differ"), { code: "weak_password", message: "must differ" }))
      .mockRejectedValueOnce(Object.assign(new Error("weak"), { code: "weak_password", message: "too common" }))
      .mockResolvedValueOnce(null);
    renderProfile({ initialTab: "settings" });

    fill("Current password", "old-password-123");
    fill("New password", "new-password-456");
    fill("Repeat new password", "something-else");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByRole("alert").textContent).toBe("The new passwords don't match.");
    expect(change).not.toHaveBeenCalled();

    fill("Repeat new password", "new-password-456");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toContain("must be different from the current one");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect((await screen.findByRole("alert")).textContent).toContain("at least 12 characters");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/All your other devices have been logged out/)).toBeTruthy();
    expect(change).toHaveBeenLastCalledWith("old-password-123", "new-password-456");
  });

  it.each([
    ["rate_limited", "Too many attempts. Please wait a few minutes."],
    ["validation_error", "Please check your inputs."],
    ["something_else", "Server says no"],
  ])("maps the %s error", async (code, text) => {
    vi.spyOn(api, "updateProfile").mockRejectedValue(Object.assign(new Error("Server says no"), { code }));
    renderProfile({ initialTab: "settings" });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toBe(text);
  });

  it("deletes the account with the password", async () => {
    const remove = vi
      .spyOn(api, "deleteAccount")
      .mockRejectedValueOnce(Object.assign(new Error("x"), { code: "invalid_password" }))
      .mockResolvedValueOnce(null);
    const { onDeleted } = renderProfile({ initialTab: "settings" });

    fireEvent.click(screen.getByRole("button", { name: /Delete account…/ }));
    fill("Confirm with your password", "secret-password");
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The current password is incorrect.");
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await vi.waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(remove).toHaveBeenCalledWith("secret-password");
  });

  it("can back out of deleting", () => {
    renderProfile({ initialTab: "settings" });
    fireEvent.click(screen.getByRole("button", { name: /Delete account…/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Confirm with your password")).toBeNull();
  });

  it("navigates between sections and signs out", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({ total_sessions: 0, quiz_questions: 0, audio_seconds: 0, sessions_this_month: 0 });
    vi.spyOn(api, "activity").mockResolvedValue([]);
    vi.spyOn(api, "payments").mockResolvedValue([]);
    const { onLogout } = renderProfile({ initialTab: "settings" });
    fireEvent.click(screen.getByRole("button", { name: /Overview/ }));
    expect(await screen.findByText("No activity yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Plan & billing/ }));
    expect(await screen.findByText("Payment history")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(onLogout).toHaveBeenCalled();
  });
});
