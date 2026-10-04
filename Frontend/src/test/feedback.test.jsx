import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import FeedbackResults from "../components/FeedbackResults.jsx";
import FeedbackView from "../components/FeedbackView.jsx";
import ParticipantView from "../components/ParticipantView.jsx";

// The server's form (sonora/feedback.py), as sent with a share link.
const SEVEN = ["1", "2", "3", "4", "5", "6", "7"];
const FORM = {
  version: 1,
  questions: [
    { id: "overall", type: "stars", label: "Overall session quality", options: ["Poor", "Fair", "Good", "Very good", "Excellent"] },
    { id: "clarity", type: "scale", label: "How clearly was the content explained?", options: SEVEN, low: "Very unclear", high: "Crystal clear" },
    { id: "pace", type: "choice", label: "How was the pace of the session?", options: ["Too slow", "Just right", "Too fast"] },
    { id: "relevance", type: "scale", label: "How relevant was the content to you?", options: SEVEN, low: "Not relevant", high: "Extremely relevant" },
    { id: "comment", type: "text", label: "Anything you'd like the trainer to know?", options: [], placeholder: "Optional", max_length: 800, required: false },
  ],
};

function answerAll() {
  fireEvent.click(screen.getByRole("button", { name: "4 stars: Very good" }));
  const clarity = screen.getByRole("group", { name: "How clearly was the content explained?" });
  fireEvent.click(within(clarity).getByRole("button", { name: "6 of 7" }));
  fireEvent.click(screen.getByRole("button", { name: "Just right" }));
  const relevance = screen.getByRole("group", { name: "How relevant was the content to you?" });
  fireEvent.click(within(relevance).getByRole("button", { name: "7 of 7" }));
}

describe("FeedbackView (listener)", () => {
  it("submits option indexes for the server's questions and a trimmed comment", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    render(<FeedbackView form={FORM} onSubmit={onSubmit} />);

    const submit = screen.getByRole("button", { name: /Submit feedback/ });
    expect(submit.disabled).toBe(true); // every rating question is required
    answerAll();
    expect(screen.getByText("Very good")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Anything you'd like the trainer to know?"), {
      target: { value: "  More examples, please.  " },
    });
    fireEvent.click(submit);

    expect(await screen.findByText("Thank you for your feedback!")).toBeTruthy();
    expect(onSubmit).toHaveBeenCalledWith({ overall: 3, clarity: 5, pace: 1, relevance: 6 }, "More examples, please.");
  });

  it("sends no comment when the text box is left empty", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    render(<FeedbackView form={FORM} onSubmit={onSubmit} />);
    answerAll();
    fireEvent.change(screen.getByLabelText("Anything you'd like the trainer to know?"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: /Submit feedback/ }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.any(Object), null));
  });

  it("thanks listeners who already answered", () => {
    render(<FeedbackView form={FORM} submitted onSubmit={vi.fn()} />);
    expect(screen.getByText("Thank you for your feedback!")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Submit feedback/ })).toBeNull();
  });

  it("shows the owner where feedback ends up instead of the form", () => {
    render(<FeedbackView form={FORM} isOwner onSubmit={vi.fn()} />);
    expect(screen.getByText("This is your session")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Submit feedback/ })).toBeNull();
  });

  it.each([
    ["feedback_already_submitted", "Thank you for your feedback!"],
    ["own_session", "This is your session"],
  ])("turns the %s answer into the matching screen", async (code, text) => {
    const onSubmit = vi.fn().mockRejectedValue(Object.assign(new Error("x"), { code }));
    render(<FeedbackView form={FORM} onSubmit={onSubmit} />);
    answerAll();
    fireEvent.click(screen.getByRole("button", { name: /Submit feedback/ }));
    expect(await screen.findByText(text)).toBeTruthy();
  });

  it.each([
    ["participant_required", /cookies must be enabled/],
    ["feedback_closed", /doesn't accept more feedback/],
    ["rate_limited", /Too many attempts/],
    ["network_error", /could not be reached/],
    ["error", /could not be sent/],
  ])("explains %s and keeps the answers for another try", async (code, message) => {
    const onSubmit = vi.fn().mockRejectedValueOnce(Object.assign(new Error("x"), { code })).mockResolvedValue(null);
    render(<FeedbackView form={FORM} onSubmit={onSubmit} />);
    answerAll();
    fireEvent.click(screen.getByRole("button", { name: /Submit feedback/ }));
    expect((await screen.findByRole("alert")).textContent).toMatch(message);
    fireEvent.click(screen.getByRole("button", { name: /Submit feedback/ }));
    expect(await screen.findByText("Thank you for your feedback!")).toBeTruthy();
  });
});

const SUMMARY = {
  responses: 4,
  comments: 3,
  questions: [
    { ...FORM.questions[0], counts: [0, 0, 1, 1, 2], answered: 4, average: 4.25 },
    { ...FORM.questions[1], counts: [0, 0, 0, 1, 1, 0, 2], answered: 4, average: 5.75 },
    { ...FORM.questions[2], counts: [0, 3, 1], answered: 4, average: null },
    { ...FORM.questions[3], counts: [0, 0, 0, 0, 0, 2, 2], answered: 4, average: 6.5 },
  ],
};

function comment(n) {
  return { id: `c${n}`, comment: `Comment ${n}`, created_at: "2026-10-04T10:00:00Z" };
}

describe("FeedbackResults (owner)", () => {
  it("shows answer shares, averages and the newest comments", async () => {
    vi.spyOn(api, "feedbackSummary").mockResolvedValue(SUMMARY);
    vi.spyOn(api, "feedbackComments").mockResolvedValue([comment(3), comment(2)]);
    render(<FeedbackResults sessionId="s1" />);

    expect(await screen.findByText("4 responses")).toBeTruthy();
    expect(screen.getByText("4.3")).toBeTruthy(); // average stars
    const pace = screen.getByText("How was the pace of the session?").closest("section");
    expect(within(pace).getByText("75% · 3")).toBeTruthy();
    expect(within(pace).queryByText(/Average/)).toBeNull(); // no average for a choice
    const stars = screen.getByText("Overall session quality").closest("section");
    const rows = within(stars).getAllByText(/★/).map((row) => row.textContent);
    expect(rows[0]).toBe("★★★★★ Excellent"); // best rating first
    expect(within(stars).getByText("50% · 2")).toBeTruthy();
    expect(screen.getByText("1 · Very unclear")).toBeTruthy();
    expect(screen.getByText("Comment 3")).toBeTruthy();
  });

  it("loads more comments on demand", async () => {
    vi.spyOn(api, "feedbackSummary").mockResolvedValue(SUMMARY);
    const comments = vi
      .spyOn(api, "feedbackComments")
      .mockResolvedValueOnce([comment(3), comment(2)])
      .mockResolvedValueOnce([comment(1)]);
    render(<FeedbackResults sessionId="s1" />);

    fireEvent.click(await screen.findByRole("button", { name: /Show more/ }));

    expect(await screen.findByText("Comment 1")).toBeTruthy();
    expect(comments).toHaveBeenLastCalledWith("s1", { limit: 20, offset: 2 });
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
  });

  it("doesn't repeat comments that moved to the next page while new ones arrived", async () => {
    vi.spyOn(api, "feedbackSummary").mockResolvedValue({ ...SUMMARY, comments: 3 });
    const pages = vi
      .spyOn(api, "feedbackComments")
      .mockResolvedValueOnce([comment(3), comment(2)])
      // Two listeners answered meanwhile: the next page repeats what was already shown.
      .mockResolvedValueOnce([comment(3), comment(2)])
      .mockResolvedValueOnce([comment(1)]);
    render(<FeedbackResults sessionId="s1" />);

    const more = await screen.findByRole("button", { name: /Show more/ });
    fireEvent.click(more);
    await vi.waitFor(() => expect(more.disabled).toBe(false));
    expect(screen.getAllByText("Comment 3")).toHaveLength(1); // not shown twice
    fireEvent.click(more);

    expect(await screen.findByText("Comment 1")).toBeTruthy();
    // The offset counts the repeated rows, so loading keeps moving forward.
    expect(pages.mock.calls.map(([, options]) => options.offset)).toEqual([undefined, 2, 4]);
  });

  it("refreshes the results on request", async () => {
    const summary = vi
      .spyOn(api, "feedbackSummary")
      .mockResolvedValueOnce(SUMMARY)
      .mockResolvedValueOnce({ ...SUMMARY, responses: 5 });
    vi.spyOn(api, "feedbackComments").mockResolvedValue([comment(3), comment(2)]);
    render(<FeedbackResults sessionId="s1" />);

    expect(await screen.findByText("4 responses")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

    expect(await screen.findByText("5 responses")).toBeTruthy();
    expect(summary).toHaveBeenCalledTimes(2);
  });

  it("removes a response after confirmation and reloads the results", async () => {
    const summary = vi
      .spyOn(api, "feedbackSummary")
      .mockResolvedValueOnce(SUMMARY)
      .mockResolvedValueOnce({ ...SUMMARY, responses: 3, comments: 2 });
    vi.spyOn(api, "feedbackComments")
      .mockResolvedValueOnce([comment(3), comment(2)])
      .mockResolvedValueOnce([comment(2)]);
    const remove = vi.spyOn(api, "deleteFeedback").mockResolvedValue(null);
    render(<FeedbackResults sessionId="s1" />);

    fireEvent.click((await screen.findAllByRole("button", { name: "Remove this response" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(await screen.findByText("3 responses")).toBeTruthy();
    expect(remove).toHaveBeenCalledWith("s1", "c3");
    expect(summary).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Comment 3")).toBeNull();
  });

  it("invites to share when nobody answered yet", async () => {
    vi.spyOn(api, "feedbackSummary").mockResolvedValue({ ...SUMMARY, responses: 0, comments: 0 });
    vi.spyOn(api, "feedbackComments").mockResolvedValue([]);
    const onShare = vi.fn();
    render(<FeedbackResults sessionId="s1" onShare={onShare} />);
    fireEvent.click(await screen.findByRole("button", { name: /Share with listeners/ }));
    expect(onShare).toHaveBeenCalled();
    expect(screen.getByText("0 responses")).toBeTruthy();
  });

  it("reports load failures", async () => {
    vi.spyOn(api, "feedbackSummary").mockRejectedValue(new Error("Server down"));
    vi.spyOn(api, "feedbackComments").mockResolvedValue([]);
    render(<FeedbackResults sessionId="s1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Server down");
  });
});

describe("ParticipantView feedback", () => {
  const SHARE = {
    title: "Vaccines",
    tabs: ["feedback"],
    script: null,
    quiz: null,
    transcript: null,
    feedback_form: FORM,
    feedback_submitted: false,
    viewer_is_owner: false,
  };

  it("submits through the share link", async () => {
    vi.spyOn(api, "publicShare").mockResolvedValue(SHARE);
    const submit = vi.spyOn(api, "submitFeedback").mockResolvedValue(null);
    render(<ParticipantView token={"t".repeat(43)} />);

    await screen.findByRole("tab", { name: /Feedback/ });
    answerAll();
    fireEvent.click(screen.getByRole("button", { name: /Submit feedback/ }));

    expect(await screen.findByText("Thank you for your feedback!")).toBeTruthy();
    expect(submit).toHaveBeenCalledWith("t".repeat(43), { overall: 3, clarity: 5, pace: 1, relevance: 6 }, null);
  });

  it("tells the owner that their input isn't counted", async () => {
    vi.spyOn(api, "publicShare").mockResolvedValue({ ...SHARE, viewer_is_owner: true });
    render(<ParticipantView token={"t".repeat(43)} />);
    expect(await screen.findByText(/This is your own share link/)).toBeTruthy();
    expect(screen.getByText("This is your session")).toBeTruthy();
  });
});
