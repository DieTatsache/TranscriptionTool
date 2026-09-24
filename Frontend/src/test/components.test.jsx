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
    expect(await screen.findByText(/ungültig, abgelaufen oder wurde vom Trainer widerrufen/)).toBeTruthy();
  });
});

describe("Login", () => {
  const meta = { password_min_length: 12, registration_enabled: true };

  function fill(label, value) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }

  it("signs in and reports failures in German", async () => {
    const onLogin = vi.fn();
    const login = vi
      .spyOn(api, "login")
      .mockRejectedValueOnce(Object.assign(new Error("x"), { code: "invalid_credentials" }))
      .mockResolvedValueOnce({ name: "Marie" });
    render(<Login mode="login" onModeChange={vi.fn()} meta={meta} onLogin={onLogin} />);

    fill("E-Mail-Adresse", "marie@example.com");
    fill("Passwort", "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText("E-Mail oder Passwort ist falsch.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    await waitFor(() => expect(onLogin).toHaveBeenCalledWith({ name: "Marie" }));
    expect(login).toHaveBeenLastCalledWith("marie@example.com", "wrong-password");
  });

  it("registers with name, email and password", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue({ name: "Ada" });
    const onLogin = vi.fn();
    render(<Login mode="register" onModeChange={vi.fn()} meta={meta} onLogin={onLogin} />);

    fill("Name", "Ada");
    fill("E-Mail-Adresse", "ada@example.com");
    fill("Passwort", "violet-harbor-lantern-42");
    fireEvent.click(screen.getByRole("button", { name: "Konto erstellen" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalled());
    expect(register).toHaveBeenCalledWith("Ada", "ada@example.com", "violet-harbor-lantern-42");
  });

  it("hides registration when it is closed", () => {
    render(<Login mode="login" onModeChange={vi.fn()} meta={{ ...meta, registration_enabled: false }} onLogin={vi.fn()} />);
    expect(screen.queryByText("Kostenlos registrieren")).toBeNull();
  });
});
