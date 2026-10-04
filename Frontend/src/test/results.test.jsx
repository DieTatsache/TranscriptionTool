import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import QrCode from "../components/QrCode.jsx";
import QuizResults from "../components/QuizResults.jsx";
import Results, { QuizView } from "../components/Results.jsx";

const DETAIL = {
  id: "s1",
  status: "ready",
  title: "Vaccines",
  script: { title: "Vaccines", summary: "How vaccines work.", overview: ["Para."], takeaways: [], questions: [] },
  quiz: [{ question: "What trains the immune system?", options: ["Vaccines", "Sleep", "Coffee"] }],
  transcript: [{ start: 0, end: 5, speaker: "Speaker", text: "Hello." }],
};

const STATS = {
  attempts: 4,
  total: 2,
  average_score: 1.5,
  score_distribution: [0, 2, 2],
  questions: [
    { question: "What trains the immune system?", options: ["Vaccines", "Sleep", "Coffee"], correct_option: 0, option_counts: [3, 1, 0], answered: 4 },
    { question: "How many doses?", options: ["One", "Two"], correct_option: 1, option_counts: [1, 2], answered: 3 },
  ],
};

describe("QuizResults", () => {
  it("shows how listeners answered each question on their first attempt", async () => {
    vi.spyOn(api, "quizResults").mockResolvedValue(STATS);
    render(<QuizResults sessionId="s1" />);

    expect(await screen.findByText("listeners")).toBeTruthy();
    expect(screen.getByText("1.5 / 2")).toBeTruthy();
    expect(screen.getByText("average score · 75%")).toBeTruthy();
    const first = screen.getByText("What trains the immune system?").closest("section");
    expect(within(first).getByText("75%")).toBeTruthy(); // answered correctly
    expect(within(first).getByText("75% · 3")).toBeTruthy();
    // The correct answer is marked with icon and label, never by colour alone.
    expect(within(first).getByText("Correct").closest(".bar-row").className).toContain("good");
    expect(within(first).getByText("Sleep").closest(".bar-row").className).toContain("muted");
    const second = screen.getByText("How many doses?").closest("section");
    expect(within(second).getByText(/1 skipped/)).toBeTruthy();
  });

  it("invites to share before anybody took the quiz", async () => {
    vi.spyOn(api, "quizResults").mockResolvedValue({ ...STATS, attempts: 0, average_score: null });
    const onShare = vi.fn();
    render(<QuizResults sessionId="s1" onShare={onShare} />);
    fireEvent.click(await screen.findByRole("button", { name: /Share with listeners/ }));
    expect(onShare).toHaveBeenCalled();
  });

  it("refreshes, e.g. once the first listeners have answered", async () => {
    const load = vi
      .spyOn(api, "quizResults")
      .mockResolvedValueOnce({ ...STATS, attempts: 0, average_score: null })
      .mockResolvedValueOnce(STATS);
    render(<QuizResults sessionId="s1" />);

    expect(await screen.findByText("No listener has taken the quiz yet")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

    expect(await screen.findByText("listeners")).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("reports errors", async () => {
    vi.spyOn(api, "quizResults").mockRejectedValue(new Error("Session not found."));
    render(<QuizResults sessionId="s1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Session not found.");
  });
});

describe("Results (owner)", () => {
  it("has feedback and analysis tabs and opens the quiz on listener results", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue(DETAIL);
    vi.spyOn(api, "quizResults").mockResolvedValue(STATS);
    const check = vi.spyOn(api, "checkQuiz").mockResolvedValue({ score: 1, total: 1, results: [], counted: false });
    render(<Results session={{ id: "s1" }} />);

    const tabs = (await screen.findAllByRole("tab")).map((t) => t.textContent);
    expect(tabs).toEqual(["Script", "Quiz", "Chatbot", "Transcript", "Feedback", "Analysis"]);
    fireEvent.click(screen.getByRole("tab", { name: /Quiz/ }));
    expect(await screen.findByText("average score · 75%")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Listener results/ }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: /Try it yourself/ }));
    fireEvent.click(screen.getByRole("button", { name: /Vaccines/ }));
    fireEvent.click(screen.getByRole("button", { name: /Check answers/ }));
    await vi.waitFor(() => expect(check).toHaveBeenCalledWith("s1", [0]));
  });

  it("shares the chatbot and feedback by default and draws QR codes without injecting markup", async () => {
    vi.spyOn(api, "getSession").mockResolvedValue(DETAIL);
    vi.spyOn(api, "listShares").mockResolvedValue([
      { id: "l1", token: "a".repeat(43), tabs: ["quiz", "feedback"], created_at: "2026-10-04T10:00:00Z", expires_at: null },
    ]);
    const create = vi.spyOn(api, "createShare").mockResolvedValue({
      id: "l2",
      token: "b".repeat(43),
      tabs: ["script"],
      created_at: "2026-10-04T10:00:00Z",
      expires_at: null,
    });
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockResolvedValue() } });
    render(<Results session={{ id: "s1" }} />);

    fireEvent.click(await screen.findByRole("button", { name: /Share with participants/ }));
    expect(screen.getByLabelText(/Feedback form/).checked).toBe(true);
    // The owner is told that the chatbot reveals the lecture even without the transcript.
    const chatbot = screen.getByLabelText(/Chatbot/);
    expect(chatbot.checked).toBe(true);
    expect(chatbot.closest("label").textContent).toContain("answers from the transcript, even if that isn't shared");
    fireEvent.click(screen.getByRole("button", { name: /Create & copy link/ }));
    await vi.waitFor(() =>
      expect(create).toHaveBeenCalledWith("s1", ["script", "quiz", "chat", "transcript", "feedback"], 30),
    );

    fireEvent.click((await screen.findAllByTitle("Show QR code"))[0]);
    const qr = screen.getByRole("img", { name: "QR code for the participant link" });
    expect(qr.tagName).toBe("svg");
    expect(qr.querySelector("path").getAttribute("d")).toMatch(/^M\d+ \d+h1v1h-1z/);
  });
});

describe("QrCode", () => {
  it("renders a scannable matrix with a quiet zone", () => {
    render(<QrCode value="https://sonora.example/share/abc" label="QR" />);
    const svg = screen.getByRole("img", { name: "QR" });
    const extent = Number(svg.getAttribute("viewBox").split(" ")[2]);
    expect(extent).toBeGreaterThanOrEqual(25); // version 2+ (21 modules) plus 2 x 2 border
    expect(svg.querySelector("rect").getAttribute("fill")).toBe("#ffffff");
  });

  it("degrades gracefully when the text can't be encoded", () => {
    render(<QrCode value={"x".repeat(5000)} label="QR" />);
    expect(screen.getByText("The QR code could not be created.")).toBeTruthy();
  });
});

describe("QuizView", () => {
  const QUIZ = [{ question: "Q?", options: ["A", "B"] }];

  it("tells listeners when their first attempt was counted", async () => {
    const onCheck = vi.fn().mockResolvedValue({
      score: 1,
      total: 1,
      counted: true,
      results: [{ selected: 0, correct_option: 0, is_correct: true, explanation: "", source_seconds: null }],
    });
    render(<QuizView quiz={QUIZ} onCheck={onCheck} />);
    fireEvent.click(screen.getByRole("button", { name: /A$/ }));
    fireEvent.click(screen.getByRole("button", { name: /Check answers/ }));
    expect(await screen.findByText(/saved anonymously/)).toBeTruthy();
  });

  it("says nothing about counting for later attempts", async () => {
    const onCheck = vi.fn().mockResolvedValue({
      score: 0,
      total: 1,
      counted: false,
      results: [{ selected: 1, correct_option: 0, is_correct: false, explanation: "", source_seconds: null }],
    });
    render(<QuizView quiz={QUIZ} onCheck={onCheck} />);
    fireEvent.click(screen.getByRole("button", { name: /B$/ }));
    fireEvent.click(screen.getByRole("button", { name: /Check answers/ }));
    await screen.findByText("0 / 1 correct");
    expect(screen.queryByText(/saved anonymously/)).toBeNull();
  });
});
