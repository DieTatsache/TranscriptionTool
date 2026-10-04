import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api.js";
import Landing from "../components/Landing.jsx";
import Login from "../components/Login.jsx";
import ParticipantView from "../components/ParticipantView.jsx";
import Results, { ScriptView, TranscriptView, VideoView } from "../components/Results.jsx";
import { copyToClipboard } from "../format.js";
import Icon from "../Icon.jsx";

const SCRIPT = {
  title: "Vaccines",
  summary: "How vaccines train the immune system.",
  overview: ["First paragraph.", "Second paragraph."],
  takeaways: [
    { text: "Vaccines create memory cells.", at_seconds: 352 },
    { text: "Side effects mean training.", at_seconds: null },
  ],
  questions: ["What is R0?"],
};
const TRANSCRIPT = [
  { start: 3, end: 9, speaker: "Speaker", text: "Hello everyone." },
  { start: 9, end: 15, speaker: "Speaker", text: "Today: vaccines." },
];

const META = {
  plans: [
    { id: "trainer", name: "Trainer", monthly_price_cents: 4900, monthly_session_limit: 10, purchasable: true },
    { id: "pro", name: "Pro", monthly_price_cents: 9900, monthly_session_limit: null, purchasable: true },
  ],
};

function clipboard(result = Promise.resolve()) {
  const writeText = vi.fn(() => result);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  return writeText;
}

afterEach(() => vi.useRealTimers());

describe("ScriptView and TranscriptView", () => {
  it("copies the script as plain text", async () => {
    const writeText = clipboard();
    render(<ScriptView script={SCRIPT} />);
    expect(screen.getByText("05:52")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Copy/ }));
    expect(await screen.findByText("Copied!")).toBeTruthy();
    expect(writeText.mock.calls[0][0]).toContain("• Vaccines create memory cells. (05:52)\n• Side effects mean training.");
  });

  it("exports the transcript with timestamps", async () => {
    const writeText = clipboard();
    render(<TranscriptView transcript={TRANSCRIPT} />);
    fireEvent.click(screen.getByRole("button", { name: /Export/ }));
    expect(await screen.findByText("Copied!")).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith("[00:03] Speaker: Hello everyone.\n[00:09] Speaker: Today: vaccines.");
  });

  it("copying fails quietly without clipboard permission", async () => {
    clipboard(Promise.reject(new Error("denied")));
    expect(await copyToClipboard("x")).toBe(false);
  });
});

describe("Chat", () => {
  async function openChat(history = []) {
    vi.spyOn(api, "getSession").mockResolvedValue({ id: "s1", status: "ready", script: SCRIPT, quiz: [], transcript: TRANSCRIPT });
    vi.spyOn(api, "chatHistory").mockResolvedValue(history);
    render(<Results session={{ id: "s1" }} />);
    fireEvent.click(await screen.findByRole("tab", { name: /Chatbot/ }));
  }

  it("answers questions and shows where an answer comes from", async () => {
    Element.prototype.scrollTo = vi.fn();
    const ask = vi
      .spyOn(api, "askChat")
      .mockResolvedValueOnce({ id: "a1", role: "assistant", content: "It is the **reproduction number**.", source: "lesson", cite_seconds: 125 })
      .mockResolvedValueOnce({ id: "a2", role: "assistant", content: "Paris.", source: "knowledge", cite_seconds: null });
    await openChat([{ id: "h1", role: "user", content: "Earlier question" }]);

    expect(await screen.findByText("Earlier question")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "What is R0?" })); // suggestion from the script
    expect(await screen.findByText("reproduction number")).toBeTruthy();
    expect(screen.getByText("reproduction number").tagName).toBe("STRONG");
    expect(screen.getByText(/From the lesson · 02:05/)).toBeTruthy();

    fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), { target: { value: "Capital of France?" } });
    fireEvent.click(screen.getByRole("button", { name: /Ask/ }));
    expect(await screen.findByText(/Not in the lesson · general knowledge/)).toBeTruthy();
    expect(ask).toHaveBeenLastCalledWith("s1", "Capital of France?");
    expect(screen.queryByText(/aren't saved/)).toBeNull(); // the owner's chat is kept
  });

  it("keeps the question when the assistant is unavailable", async () => {
    Element.prototype.scrollTo = vi.fn();
    vi.spyOn(api, "askChat").mockRejectedValue(new Error("The assistant is not available right now."));
    await openChat();
    const input = screen.getByRole("textbox", { name: "Your question" });
    fireEvent.change(input, { target: { value: "Why?" } });
    fireEvent.submit(input.closest("form"));
    expect((await screen.findByRole("alert")).textContent).toContain("not available right now");
    expect(input.value).toBe("Why?");
  });
});

describe("Share dialog", () => {
  const LINK = { id: "l1", token: "a".repeat(43), tabs: ["quiz"], created_at: "2026-10-04T10:00:00Z", expires_at: "2026-11-03T10:00:00Z" };

  async function openShare() {
    vi.spyOn(api, "getSession").mockResolvedValue({ id: "s1", status: "ready", script: SCRIPT, quiz: [], transcript: [] });
    render(<Results session={{ id: "s1" }} />);
    fireEvent.click(await screen.findByRole("button", { name: /Share with participants/ }));
  }

  it("copies and revokes links", async () => {
    vi.spyOn(api, "listShares").mockResolvedValue([LINK]);
    const revoke = vi.spyOn(api, "revokeShare").mockResolvedValue(null);
    const writeText = clipboard();
    await openShare();

    expect(await screen.findByText("created Oct 4, 2026 · valid until Nov 3, 2026")).toBeTruthy();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Copy" }));
    expect(await screen.findByText("Copied!")).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/share/${LINK.token}`);
    fireEvent.click(screen.getByRole("button", { name: "Revoke link" }));
    expect(await screen.findByText("No links created yet.")).toBeTruthy();
    expect(revoke).toHaveBeenCalledWith("s1", "l1");
  });

  it("needs at least one tab, offers permanent links and closes with Escape", async () => {
    vi.spyOn(api, "listShares").mockResolvedValue([]);
    const create = vi.spyOn(api, "createShare").mockRejectedValue(new Error("Only finished sessions can be shared."));
    await openShare();

    for (const label of [/Script & summary/, /Quiz/, /Chatbot/, /Transcript/, /Feedback form/]) {
      fireEvent.click(screen.getByLabelText(label));
    }
    expect(screen.getByText("Select at least one section to share.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Create & copy link/ }).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Quiz/));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "never" } });
    fireEvent.click(screen.getByRole("button", { name: /Create & copy link/ }));
    expect(await screen.findByText("Only finished sessions can be shared.")).toBeTruthy();
    expect(create).toHaveBeenCalledWith("s1", ["quiz"], null);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("reports when existing links can't be loaded", async () => {
    vi.spyOn(api, "listShares").mockRejectedValue(new Error("offline"));
    await openShare();
    expect(await screen.findByText("offline")).toBeTruthy();
  });
});

describe("VideoView (design mock)", () => {
  it("plays and seeks", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<VideoView />);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
    const bar = document.querySelector(".video-progress");
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });
    fireEvent.click(bar, { clientX: 99 });
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(screen.getByText("1:28 / 1:28")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy(); // stopped at the end
  });
});

describe("Landing", () => {
  it("leads visitors to sign-up with the chosen plan or to the sign-in", () => {
    const onEnter = vi.fn();
    render(<Landing onEnter={onEnter} meta={META} />);
    const pricing = document.getElementById("pricing");
    expect(within(pricing).getByText("€49")).toBeTruthy();
    fireEvent.click(within(pricing).getByRole("button", { name: "Get Pro" }));
    expect(onEnter).toHaveBeenLastCalledWith("register", "pro");
    fireEvent.click(screen.getAllByRole("button", { name: "Log in" })[0]);
    expect(onEnter).toHaveBeenLastCalledWith("login");
    fireEvent.click(screen.getAllByRole("button", { name: /Create your account/ })[0]);
    expect(onEnter).toHaveBeenLastCalledWith("register");
  });

  it("offers the free plan first when the server has a free tier", () => {
    const onEnter = vi.fn();
    const free = { id: "free", name: "Free", monthly_price_cents: 0, monthly_session_limit: 1, max_audio_minutes: 60, purchasable: false };
    render(<Landing onEnter={onEnter} meta={{ ...META, plans: [free, ...META.plans] }} />);

    const pricing = document.getElementById("pricing");
    expect(within(pricing).getByText("€0")).toBeTruthy();
    expect(within(pricing).getByText("Recordings up to 60 min")).toBeTruthy();
    fireEvent.click(within(pricing).getByRole("button", { name: "Start for free" }));
    expect(onEnter).toHaveBeenLastCalledWith("register", "free");
    fireEvent.click(screen.getAllByRole("button", { name: /Start for free/ })[0]); // the hero
    expect(onEnter).toHaveBeenLastCalledWith("register", "free");
  });

  it("features what the product really does", () => {
    render(<Landing onEnter={vi.fn()} meta={META} />);
    for (const kicker of ["The recap script", "The quiz", "Listener feedback", "Lecture analysis"]) {
      expect(screen.getByText(kicker)).toBeTruthy();
    }
    expect(screen.getByRole("img", { name: /Example lecture scores/ })).toBeTruthy();
    // Nothing the product can't do (yet): no recap video, speaker separation or branding.
    expect(document.body.textContent).not.toMatch(/video|speakers are separated|branding/i);
  });

  it("shows no prices before the server's catalog has loaded", () => {
    render(<Landing onEnter={vi.fn()} meta={null} />);
    const pricing = document.getElementById("pricing");
    expect(within(pricing).getByRole("status").textContent).toContain("Loading plans");
    expect(within(pricing).queryByText(/€/)).toBeNull();
  });
});

describe("Login errors", () => {
  it.each([
    ["login_locked", "Too many failed attempts"],
    ["rate_limited", "Too many requests"],
    ["email_taken", "already exists"],
    ["weak_password", "at least 12 characters"],
    ["registration_disabled", "Registration is currently closed."],
    ["validation_error", "Please check your inputs."],
    ["network_error", "The server is unreachable."],
    ["something_else", "Something went wrong."],
  ])("explains %s", async (code, message) => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(400, code, "x"));
    render(<Login mode="login" onModeChange={vi.fn()} meta={{ password_min_length: 12 }} onLogin={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect((await screen.findByRole("alert")).textContent).toContain(message);
  });

  it("switches to registration and shows a notice", () => {
    const onModeChange = vi.fn();
    render(<Login mode="login" onModeChange={onModeChange} meta={null} notice="Session expired." onLogin={vi.fn()} />);
    expect(screen.getByText("Session expired.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
    expect(onModeChange).toHaveBeenCalledWith("register");
  });
});

describe("ParticipantView", () => {
  const SHARE = { title: "Vaccines", tabs: ["script", "quiz", "transcript"], script: SCRIPT, quiz: [{ question: "Q?", options: ["A", "B"] }], transcript: TRANSCRIPT };

  it("switches between the shared tabs and grades the quiz through the link", async () => {
    vi.spyOn(api, "publicShare").mockResolvedValue(SHARE);
    const check = vi.spyOn(api, "checkSharedQuiz").mockResolvedValue({
      score: 1,
      total: 1,
      counted: true,
      results: [{ selected: 0, correct_option: 0, is_correct: true, explanation: "", source_seconds: null }],
    });
    render(<ParticipantView token={"t".repeat(43)} />);

    expect(await screen.findByText("How vaccines train the immune system.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: /Transcript/ }));
    expect(screen.getByText("Hello everyone.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: /Quiz/ }));
    fireEvent.click(screen.getByRole("button", { name: /A$/ }));
    fireEvent.click(screen.getByRole("button", { name: /Check answers/ }));
    expect(await screen.findByText(/saved anonymously/)).toBeTruthy();
    expect(check).toHaveBeenCalledWith("t".repeat(43), [0]);
  });

  it.each([
    [429, /Too many requests/],
    [500, /could not be loaded/],
  ])("explains load errors (%s)", async (status, message) => {
    vi.spyOn(api, "publicShare").mockRejectedValue(new ApiError(status, "x", "y"));
    render(<ParticipantView token={"t".repeat(43)} />);
    expect(await screen.findByText(message)).toBeTruthy();
  });
});

describe("ParticipantView chat", () => {
  const TOKEN = "t".repeat(43);
  const CHAT_SHARE = { title: "Vaccines", tabs: ["script", "chat"], script: SCRIPT };

  async function openChat(share = CHAT_SHARE) {
    Element.prototype.scrollTo = vi.fn();
    vi.spyOn(api, "publicShare").mockResolvedValue(share);
    render(<ParticipantView token={TOKEN} />);
    if (share.tabs[0] !== "chat") fireEvent.click(await screen.findByRole("tab", { name: /Chatbot/ }));
    return screen.findByRole("textbox", { name: "Your question" });
  }

  function askQuestion(input, question) {
    fireEvent.change(input, { target: { value: question } });
    fireEvent.submit(input.closest("form"));
  }

  it("answers through the link and sends the conversation along, since nothing is stored", async () => {
    const ask = vi
      .spyOn(api, "askSharedChat")
      .mockResolvedValueOnce({ answer: "It is the **reproduction number**.", source: "lesson", cite_seconds: 125 })
      .mockResolvedValueOnce({ answer: "I can only help with this lecture.", source: "knowledge", cite_seconds: null });
    const input = await openChat();

    expect(screen.getByText(/aren't saved and the trainer can't see them/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "What is R0?" })); // suggestion from the script
    expect((await screen.findByText("reproduction number")).tagName).toBe("STRONG");
    expect(screen.getByText(/From the lesson · 02:05/)).toBeTruthy();
    expect(ask).toHaveBeenLastCalledWith(TOKEN, "What is R0?", []);

    askQuestion(input, "Capital of France?");
    expect(await screen.findByText("I can only help with this lecture.")).toBeTruthy();
    expect(ask).toHaveBeenLastCalledWith(TOKEN, "Capital of France?", [
      { role: "user", content: "What is R0?" },
      { role: "assistant", content: "It is the **reproduction number**." },
    ]);
  });

  it("keeps the conversation while other tabs are open", async () => {
    vi.spyOn(api, "askSharedChat").mockResolvedValue({ answer: "Memory cells.", source: "lesson", cite_seconds: null });
    askQuestion(await openChat(), "What do vaccines create?");
    await screen.findByText("Memory cells.");

    fireEvent.click(screen.getByRole("tab", { name: /Script/ }));
    expect(screen.getByText("How vaccines train the immune system.")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Your question" })).toBeNull(); // hidden
    fireEvent.click(screen.getByRole("tab", { name: /Chatbot/ }));
    expect(screen.getByText("What do vaccines create?")).toBeTruthy();
    expect(screen.getByText("Memory cells.")).toBeTruthy();
  });

  it("sends at most the last six turns", async () => {
    const ask = vi
      .spyOn(api, "askSharedChat")
      .mockImplementation(async (_, question) => ({ answer: `A: ${question}`, source: "knowledge", cite_seconds: null }));
    const input = await openChat();

    for (const question of ["Q1", "Q2", "Q3", "Q4", "Q5"]) {
      askQuestion(input, question);
      await screen.findByText(`A: ${question}`);
    }

    const history = ask.mock.calls.at(-1)[2];
    expect(history.map((turn) => turn.content)).toEqual(["Q2", "A: Q2", "Q3", "A: Q3", "Q4", "A: Q4"]);
  });

  it("explains when the assistant is busy and keeps the question", async () => {
    vi.spyOn(api, "askSharedChat").mockRejectedValue(
      new ApiError(503, "assistant_busy", "The assistant is busy right now. Please try again in a minute."),
    );
    // Only the chat is shared: it opens right away, with general suggestions.
    const input = await openChat({ title: "Vaccines", tabs: ["chat"], script: null });
    expect(screen.getByRole("button", { name: "Summarize the key points" })).toBeTruthy();

    askQuestion(input, "Why?");

    expect((await screen.findByRole("alert")).textContent).toContain("busy right now");
    expect(input.value).toBe("Why?");
    expect(screen.queryByText("Why?", { selector: ".chat-bubble" })).toBeNull();
  });
});

describe("Icon", () => {
  it("fills the play icon and strokes the others", () => {
    const { container } = render(
      <>
        <Icon name="play" />
        <Icon name="chart" />
      </>,
    );
    const [play, chart] = container.querySelectorAll("svg");
    expect(play.getAttribute("fill")).toBe("currentColor");
    expect(chart.getAttribute("stroke")).toBe("currentColor");
  });
});
