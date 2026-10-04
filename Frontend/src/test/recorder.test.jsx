import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api.js";
import Recorder from "../components/Recorder.jsx";
import { audioDuration } from "../media.js";

// Reading a file's duration needs real media decoding; each test says what it "reads".
vi.mock("../media.js", () => ({ audioDuration: vi.fn(async () => null) }));

const META = {
  max_upload_mb: 1,
  max_audio_minutes: 1,
  languages: [
    { code: "de", name: "German" },
    { code: "en", name: "English" },
  ],
};
const USAGE = {
  plan: { id: "trainer", name: "Trainer", monthly_session_limit: 10 },
  sessions_this_month: 0,
  remaining_this_month: 10,
};

class FakeMediaRecorder {
  static isTypeSupported = (type) => type === "audio/webm;codecs=opus";
  static last = null;

  constructor(stream, options) {
    this.stream = stream;
    this.mimeType = options.mimeType;
    this.state = "inactive";
    FakeMediaRecorder.last = this;
  }
  start() {
    this.state = "recording";
  }
  pause() {
    this.state = "paused";
  }
  resume() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["audio-bytes"]) });
    this.onstop?.();
  }
}

class FakeAudioContext {
  createAnalyser() {
    return { fftSize: 0, frequencyBinCount: 8, getByteFrequencyData: (data) => data.fill(128) };
  }
  createMediaStreamSource() {
    return { connect() {} };
  }
  close() {}
}

let track;

beforeEach(() => {
  track = { stop: vi.fn() };
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
  });
});

afterEach(() => {
  vi.useRealTimers();
  delete navigator.mediaDevices;
});

function renderRecorder(props = {}) {
  const handlers = { onUploaded: vi.fn(), onCancel: vi.fn(), onChoosePlan: vi.fn() };
  const view = render(<Recorder meta={META} usage={USAGE} {...handlers} {...props} />);
  return { ...view, ...handlers, fileInput: view.container.querySelector('input[type="file"]') };
}

function audioFile(size = 2048, name = "talk.webm") {
  return new File([new Uint8Array(size)], name, { type: "audio/webm" });
}

describe("Recorder: the plan's recording length", () => {
  const FREE_USAGE = {
    plan: { id: "free", name: "Free", monthly_session_limit: 1, max_audio_minutes: 60 },
    sessions_this_month: 0,
    remaining_this_month: 1,
  };
  const LONG_META = { ...META, max_upload_mb: 200, max_audio_minutes: 180 };

  it("refuses a file longer than the plan allows before uploading it", async () => {
    const upload = vi.spyOn(api, "uploadRecording");
    vi.mocked(audioDuration).mockResolvedValueOnce(65 * 60);
    const { fileInput } = renderRecorder({ meta: LONG_META, usage: FREE_USAGE });

    expect(screen.getByText(/at most 1h 00m/)).toBeTruthy(); // the free plan's 60 minutes
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });

    expect((await screen.findByRole("alert")).textContent).toBe(
      "This recording is 1h 05m long. Your plan allows recordings of up to 1h 00m.",
    );
    expect(upload).not.toHaveBeenCalled();
  });

  it("uploads files within the limit, and files whose length the browser can't read", async () => {
    const upload = vi.spyOn(api, "uploadRecording").mockResolvedValue({ id: "s1", status: "queued" });
    vi.mocked(audioDuration).mockResolvedValueOnce(59 * 60).mockResolvedValueOnce(null);
    const { fileInput } = renderRecorder({ meta: LONG_META, usage: FREE_USAGE });

    fireEvent.change(fileInput, { target: { files: [audioFile()] } });
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
  });
});

describe("Recorder: uploading a file", () => {
  it("uploads with the chosen language and reports progress", async () => {
    const upload = vi.spyOn(api, "uploadRecording").mockImplementation((_file, { onProgress }) => {
      onProgress(0.5);
      return new Promise(() => {}); // still uploading
    });
    const { fileInput } = renderRecorder();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "de" } });
    expect(screen.getByText("Language: German")).toBeTruthy();
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });

    expect(await screen.findByText("50%")).toBeTruthy();
    expect(upload).toHaveBeenCalledWith(expect.any(File), expect.objectContaining({ language: "de" }));
  });

  it("hands the created session to the app", async () => {
    vi.spyOn(api, "uploadRecording").mockResolvedValue({ id: "s1", status: "queued" });
    const { fileInput, onUploaded } = renderRecorder();
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalledWith({ id: "s1", status: "queued" }));
  });

  it("refuses files above the upload limit before sending anything", () => {
    const upload = vi.spyOn(api, "uploadRecording");
    const { fileInput } = renderRecorder();
    fireEvent.change(fileInput, { target: { files: [audioFile(2 * 1024 * 1024)] } });
    expect(screen.getByRole("alert").textContent).toContain("larger than 1 MB");
    expect(upload).not.toHaveBeenCalled();
  });

  it.each([
    ["unsupported_audio", "This file type is not supported."],
    ["payload_too_large", "The file is too large."],
    ["audio_too_short", "The recording is empty or too short."],
    ["rate_limited", "Too many uploads"],
    ["plan_required", "Choose a plan to upload recordings."],
    ["quota_exceeded", "You have used all 10 sessions"],
  ])("explains %s and keeps the recording for a retry", async (code, message) => {
    const upload = vi
      .spyOn(api, "uploadRecording")
      .mockRejectedValueOnce(new ApiError(400, code, "You have used all 10 sessions of your Trainer plan."))
      .mockResolvedValue({ id: "s1" });
    const { fileInput, onUploaded } = renderRecorder();
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    fireEvent.click(screen.getByRole("button", { name: /Retry upload/ }));
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalled());
    expect(upload).toHaveBeenCalledTimes(2);
  });

  it("can save a recording whose upload failed", async () => {
    vi.spyOn(api, "uploadRecording").mockRejectedValue(new ApiError(0, "network_error", "offline"));
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { fileInput } = renderRecorder();
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });

    fireEvent.click(await screen.findByRole("button", { name: /Save recording/ }));
    expect(click).toHaveBeenCalledOnce();
  });

  it("can be cancelled while uploading", async () => {
    let signal;
    vi.spyOn(api, "uploadRecording").mockImplementation((_file, options) => {
      signal = options.signal;
      return new Promise((_, reject) =>
        options.signal.addEventListener("abort", () => reject(new DOMException("x", "AbortError"))),
      );
    });
    const { fileInput, onCancel } = renderRecorder();
    fireEvent.change(fileInput, { target: { files: [audioFile()] } });
    await vi.waitFor(() => expect(signal).toBeDefined()); // the upload is running
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(signal.aborted).toBe(true);
    expect(onCancel).toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Recorder: recording", () => {
  it("records, pauses, resumes and uploads the result", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const upload = vi.spyOn(api, "uploadRecording").mockResolvedValue({ id: "s1" });
    const { onUploaded } = renderRecorder();

    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    expect(await screen.findByText("Recording")).toBeTruthy();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(screen.getByText("00:02")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Pause/ }));
    expect(screen.getByText("Paused")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Resume/ }));
    fireEvent.click(screen.getByRole("button", { name: /Stop & analyze/ }));

    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalledWith({ id: "s1" }));
    const file = upload.mock.calls[0][0];
    expect(file.type).toBe("audio/webm;codecs=opus");
    expect(file.name).toMatch(/^recording-.*\.webm$/);
    expect(track.stop).toHaveBeenCalled(); // the microphone is released
  });

  it("stops automatically at the maximum length", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(api, "uploadRecording").mockResolvedValue({ id: "s1" });
    const { onUploaded } = renderRecorder();
    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    await screen.findByText("Recording");
    await act(() => vi.advanceTimersByTimeAsync(61_000)); // max_audio_minutes = 1
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalled());
  });

  it("discards a recording without uploading it", async () => {
    const upload = vi.spyOn(api, "uploadRecording");
    const { onCancel } = renderRecorder();
    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    expect(onCancel).toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
  });

  it("explains a denied microphone", async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValue(Object.assign(new Error("no"), { name: "NotAllowedError" }));
    renderRecorder();
    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("Microphone access was denied");
  });

  it("explains other recording errors", async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValue(new Error("device busy"));
    renderRecorder();
    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("Could not start recording: device busy");
  });

  it("falls back to uploads in browsers without recording support", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    renderRecorder();
    fireEvent.click(screen.getByRole("button", { name: /Start recording/ }));
    expect(screen.getByRole("alert").textContent).toContain("Recording is not supported in this browser");
  });
});
