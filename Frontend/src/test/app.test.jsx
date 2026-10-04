import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setCsrfToken } from "../api.js";
import App from "../App.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Processing from "../components/Processing.jsx";

const META = { password_min_length: 12, registration_enabled: true, languages: [], max_upload_mb: 200, max_audio_minutes: 180 };
const USER = { id: "u1", name: "Ada Lovelace", email: "ada@example.com", bio: "", plan: "trainer", notify_on_ready: true };
const USAGE = {
  plan: { id: "trainer", name: "Trainer", monthly_price_cents: 4900, monthly_session_limit: 10, purchasable: true },
  sessions_this_month: 2,
  remaining_this_month: 8,
};

function session(overrides) {
  return {
    id: "s1",
    title: "Vaccines",
    status: "ready",
    error_message: null,
    language: "en",
    duration_seconds: 1500,
    quiz_count: 5,
    created_at: "2026-10-01T10:00:00Z",
    ready_at: "2026-10-01T10:05:00Z",
    ...overrides,
  };
}

function signedIn(sessions) {
  vi.spyOn(api, "meta").mockResolvedValue(META);
  vi.spyOn(api, "me").mockResolvedValue(USER);
  vi.spyOn(api, "usage").mockResolvedValue(USAGE);
  return vi.spyOn(api, "listSessions").mockResolvedValue(sessions);
}

afterEach(() => {
  vi.useRealTimers();
  setCsrfToken(null);
});

describe("App", () => {
  it("shows the landing page to visitors and opens the sign-in", async () => {
    vi.spyOn(api, "meta").mockResolvedValue(META);
    vi.spyOn(api, "me").mockRejectedValue(new ApiError(401, "not_authenticated", "x"));
    render(<App />);

    fireEvent.click((await screen.findAllByRole("button", { name: "Log in" }))[0]);
    expect(screen.getByText("Welcome back")).toBeTruthy();
  });

  it("opens the newest session of a signed-in trainer", async () => {
    signedIn([session(), session({ id: "s0", title: "Older", duration_seconds: 600, quiz_count: 3 })]);
    vi.spyOn(api, "getSession").mockResolvedValue({
      ...session(),
      script: { title: "Vaccines", summary: "How vaccines work.", overview: ["Para."], takeaways: [], questions: [] },
      quiz: [],
      transcript: [],
    });
    render(<App />);

    expect(await screen.findByText("How vaccines work.")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Vaccines");
    expect(screen.getByText("2 of 10 sessions this month")).toBeTruthy();
    expect(screen.getByText(/25 min · 5 quiz Qs/)).toBeTruthy();
  });

  it("polls while a session is processing and shows the result when ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const list = signedIn([session()]); // ready from the third request on
    list.mockResolvedValueOnce([session({ status: "transcribing" })]).mockResolvedValueOnce([session({ status: "generating" })]);
    vi.spyOn(api, "getSession").mockResolvedValue({ ...session(), script: null, quiz: null, transcript: null });
    render(<App />);

    expect(await screen.findByText("Analyzing what was said", { selector: "h2" })).toBeTruthy();
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByText("Writing the recap & quiz").closest("li").className).toContain("active");
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(await screen.findByRole("tab", { name: /Script/ })).toBeTruthy();
    const calls = list.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(list.mock.calls.length).toBe(calls); // no polling once everything is ready
  });

  it("retries a failed session", async () => {
    signedIn([session({ status: "failed", error_message: "No speech was detected in the recording." })]);
    const retry = vi.spyOn(api, "retrySession").mockResolvedValue(session({ status: "queued" }));
    render(<App />);

    expect(await screen.findByText("No speech was detected in the recording.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText("Waiting for a free worker")).toBeTruthy();
    expect(retry).toHaveBeenCalledWith("s1");
  });

  it("deletes a session after confirmation", async () => {
    signedIn([session({ status: "queued" }), session({ id: "s2", title: "Second", status: "queued" })]);
    const remove = vi.spyOn(api, "deleteSession").mockResolvedValue(null);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete Vaccines" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }));

    await vi.waitFor(() => expect(screen.queryByRole("button", { name: "Delete Vaccines" })).toBeNull());
    expect(remove).toHaveBeenCalledWith("s1");
    expect(screen.getByRole("button", { name: "Delete Second" })).toBeTruthy();
  });

  it("reports failed actions in a dismissible banner", async () => {
    signedIn([session({ status: "failed" })]);
    vi.spyOn(api, "retrySession").mockRejectedValue(new Error("Only failed sessions can be retried."));
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Try again/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("Only failed sessions can be retried.");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("starts with an empty state and opens the recorder", async () => {
    signedIn([]);
    render(<App />);
    const empty = (await screen.findByText("Record your first session")).closest(".empty-state");
    fireEvent.click(within(empty).getByRole("button", { name: /New session/ }));
    expect(await screen.findByText("Ready to record")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Record your first session")).toBeTruthy();
  });

  it("returns to the sign-in with a notice when the session expires", async () => {
    const responses = {
      "/api/v1/meta": [200, META],
      "/api/v1/auth/me": [200, { user: USER, csrf_token: "csrf" }],
      "/api/v1/sessions": [401, { error: { code: "session_expired", message: "Expired" } }],
      "/api/v1/me/usage": [200, USAGE],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const [status, body] = responses[url];
        return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      }),
    );
    render(<App />);

    expect(await screen.findByText("Your session has expired. Please log in again.")).toBeTruthy();
    expect(screen.getByText("Welcome back")).toBeTruthy();
  });

  it("signs out from the profile", async () => {
    signedIn([]);
    vi.spyOn(api, "stats").mockResolvedValue({ total_sessions: 0, quiz_questions: 0, audio_seconds: 0, sessions_this_month: 0 });
    vi.spyOn(api, "activity").mockResolvedValue([]);
    const logout = vi.spyOn(api, "logout").mockResolvedValue(null);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Open profile" }));
    expect(await screen.findByText("Overview", { selector: "h2" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByText(/Turn what you/)).toBeTruthy();
    expect(logout).toHaveBeenCalled();
  });
});

describe("Processing", () => {
  it.each([
    ["queued", "Waiting for a free worker"],
    ["transcribing", "Transcribing audio"],
    ["generating", "Writing the recap & quiz"],
  ])("marks the %s step as active", (status, label) => {
    render(<Processing session={{ status }} onRetry={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText(label).closest("li").className).toContain("active");
    expect(screen.getByText("Recording uploaded").closest("li").className).toContain("done");
  });

  it("offers retry and delete for failed sessions", () => {
    const onRetry = vi.fn();
    const onDelete = vi.fn();
    render(<Processing session={{ status: "failed", error_message: null }} onRetry={onRetry} onDelete={onDelete} />);
    expect(screen.getByText("Something went wrong while processing the recording.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledOnce();
  });
});

describe("ConfirmDialog", () => {
  it("cancels with Escape or a click outside, confirms with its button", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    const { container } = render(
      <ConfirmDialog title="Delete?" confirmLabel="Delete" onConfirm={onConfirm} onCancel={onCancel}>
        Gone for good.
      </ConfirmDialog>,
    );
    // Rendered into <body>, outside any (possibly transformed) parent.
    expect(container.querySelector(".modal-backdrop")).toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(document.body.querySelector(".modal-backdrop"));
    fireEvent.click(screen.getByRole("alertdialog")); // clicks inside don't cancel
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
