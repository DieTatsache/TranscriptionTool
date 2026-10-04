import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import Login from "../components/Login.jsx";
import ParticipantView from "../components/ParticipantView.jsx";
import { QuizView } from "../components/Results.jsx";

const QUIZ = [
  { question: "An objection is…", options: ["A rejection", "A request for information"] },
  { question: "Pause for…", options: ["A full breath", "A minute"] },
];

describe("QuizView", () => {
  it("lets the server grade answers and only then reveals the solution", async () => {
    const onCheck = vi.fn().mockResolvedValue({
      score: 1,
      total: 2,
      results: [
        { selected: 1, correct_option: 1, is_correct: true, explanation: "Said at the start.", source_seconds: 41 },
        { selected: 1, correct_option: 0, is_correct: false, explanation: "A full breath.", source_seconds: 250 },
      ],
    });
    render(<QuizView quiz={QUIZ} onCheck={onCheck} />);

    const check = screen.getByRole("button", { name: /check answers/i });
    expect(check.disabled).toBe(true); // every question must be answered first
    fireEvent.click(screen.getByRole("button", { name: /A request for information/ }));
    fireEvent.click(screen.getByRole("button", { name: /A minute/ }));
    expect(screen.queryByText("Said at the start.")).toBeNull();
    fireEvent.click(check);

    await screen.findByText("1 / 2 correct");
    expect(onCheck).toHaveBeenCalledWith([1, 1]);
    expect(screen.getByText("said at 00:41")).toBeTruthy();
    expect(screen.getByRole("button", { name: /A full breath/ }).className).toContain("correct");
    expect(screen.getByRole("button", { name: /A minute/ }).className).toContain("wrong");
  });

  it("shows grading errors", async () => {
    render(<QuizView quiz={QUIZ.slice(0, 1)} onCheck={vi.fn().mockRejectedValue(new Error("Offline"))} />);
    fireEvent.click(screen.getByRole("button", { name: /A rejection/ }));
    fireEvent.click(screen.getByRole("button", { name: /check answers/i }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Offline"));
  });
});

describe("ParticipantView", () => {
  it("shows only the tabs the trainer shared", async () => {
    vi.spyOn(api, "publicShare").mockResolvedValue({
      title: "Handling Objections",
      tabs: ["quiz"],
      quiz: QUIZ,
      script: null,
      transcript: null,
    });
    render(<ParticipantView token={"t".repeat(43)} />);
    expect(await screen.findByRole("tab", { name: /quiz/i })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /script/i })).toBeNull();
    expect(screen.queryByRole("tab", { name: /transcript/i })).toBeNull();
    expect(screen.getByText("An objection is…")).toBeTruthy();
  });

  it("explains invalid or revoked links", async () => {
    vi.spyOn(api, "publicShare").mockRejectedValue(Object.assign(new Error("gone"), { status: 404 }));
    render(<ParticipantView token={"t".repeat(43)} />);
    expect(await screen.findByText(/invalid, has expired, or was revoked by the trainer/)).toBeTruthy();
  });
});

describe("Login", () => {
  const meta = {
    password_min_length: 12,
    registration_enabled: true,
    plans: [
      { id: "trainer", name: "Trainer", monthly_price_cents: 4900, monthly_session_limit: 10, purchasable: true },
      { id: "pro", name: "Pro", monthly_price_cents: 9900, monthly_session_limit: null, purchasable: true },
    ],
  };

  function fill(label, value) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }

  it("signs in and reports failures in English", async () => {
    const onLogin = vi.fn();
    const login = vi
      .spyOn(api, "login")
      .mockRejectedValueOnce(Object.assign(new Error("x"), { code: "invalid_credentials" }))
      .mockResolvedValueOnce({ name: "Marie" });
    render(<Login mode="login" onModeChange={vi.fn()} meta={meta} onLogin={onLogin} />);

    fill("Email address", "marie@example.com");
    fill("Password", "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Email or password is incorrect.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith({ name: "Marie" }));
    expect(login).toHaveBeenLastCalledWith("marie@example.com", "wrong-password");
  });

  function payWith(number) {
    fill("Cardholder name", "Ada Lovelace");
    fill("Card number", number);
    fill("Expiry", "12/40");
    fill("CVC", "123");
    fireEvent.click(screen.getByRole("button", { name: /^Pay / }));
  }

  it("registers without a plan, then buys the chosen plan in the checkout", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue({ name: "Ada", plan: "none" });
    const checkout = vi.spyOn(api, "checkout").mockResolvedValue({ user: { name: "Ada", plan: "trainer" } });
    const onLogin = vi.fn();
    render(<Login mode="register" onModeChange={vi.fn()} meta={meta} onLogin={onLogin} plan="trainer" />);

    fill("Name", "Ada");
    fill("Email address", "ada@example.com");
    fill("Password", "violet-harbor-lantern-42");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Subscribe to Trainer")).toBeTruthy();
    // The client never chooses its plan at sign-up: only the checkout grants it.
    expect(register).toHaveBeenCalledWith("Ada", "ada@example.com", "violet-harbor-lantern-42");
    payWith("4242 4242 4242 4242");
    expect(await screen.findByText("Payment confirmed")).toBeTruthy();
    expect(checkout).toHaveBeenCalledWith("trainer", "tok_visa");
    fireEvent.click(screen.getByRole("button", { name: /Go to my account/ }));
    expect(onLogin).toHaveBeenCalledWith({ name: "Ada", plan: "trainer" });
  });

  it("registers on the free plan without any checkout", async () => {
    const free = { id: "free", name: "Free", monthly_price_cents: 0, monthly_session_limit: 1, max_audio_minutes: 60, purchasable: false };
    vi.spyOn(api, "register").mockResolvedValue({ name: "Ada", plan: "free" });
    const checkout = vi.spyOn(api, "checkout");
    const onLogin = vi.fn();
    render(
      <Login mode="register" onModeChange={vi.fn()} meta={{ ...meta, plans: [free, ...meta.plans] }} onLogin={onLogin} plan="free" />,
    );

    fill("Name", "Ada");
    fill("Email address", "ada@example.com");
    fill("Password", "violet-harbor-lantern-42");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith({ name: "Ada", plan: "free" }));
    expect(screen.queryByText(/Subscribe to/)).toBeNull();
    expect(checkout).not.toHaveBeenCalled();
  });

  it("signs in without a plan when the checkout is cancelled", async () => {
    vi.spyOn(api, "register").mockResolvedValue({ name: "Ada", plan: "none" });
    const checkout = vi.spyOn(api, "checkout");
    const onLogin = vi.fn();
    render(<Login mode="register" onModeChange={vi.fn()} meta={meta} onLogin={onLogin} plan="pro" />);

    fill("Name", "Ada");
    fill("Email address", "ada@example.com");
    fill("Password", "violet-harbor-lantern-42");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(onLogin).toHaveBeenCalledWith({ name: "Ada", plan: "none" });
    expect(checkout).not.toHaveBeenCalled();
  });

  it("starts registration with the plan picker, priced by the server", async () => {
    const onModeChange = vi.fn();
    const priced = {
      ...meta,
      plans: [
        { id: "trainer", name: "Trainer", monthly_price_cents: 5900, monthly_session_limit: 12 },
        { id: "pro", name: "Pro", monthly_price_cents: 9900, monthly_session_limit: null },
      ],
    };
    render(<Login mode="register" onModeChange={onModeChange} meta={priced} onLogin={vi.fn()} />);

    expect(screen.getByText("Choose your plan")).toBeTruthy();
    expect(screen.getByText("€59")).toBeTruthy();
    expect(screen.getByText("12 sessions / month")).toBeTruthy();
    expect(screen.getByText("Unlimited sessions")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Get Pro" }));
    expect(await screen.findByLabelText("Name")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(onModeChange).toHaveBeenCalledWith("login");
  });

  it("hides registration when it is closed", () => {
    render(<Login mode="login" onModeChange={vi.fn()} meta={{ ...meta, registration_enabled: false }} onLogin={vi.fn()} />);
    expect(screen.queryByText("Create an account")).toBeNull();
  });
});
