import { afterEach, describe, expect, it, vi } from "vitest";
import { audioDuration } from "../media.js";

// A stand-in for the browser's <audio>: reports metadata (or an error) once given a source.
function fakeAudio(outcome) {
  return class {
    set src(url) {
      this.url = url;
      if (outcome === "never") return;
      setTimeout(() => {
        if (outcome === "error") this.onerror?.();
        else {
          this.duration = outcome;
          this.onloadedmetadata?.();
        }
      }, 0);
    }
  };
}

function stubUrls() {
  const revoked = [];
  vi.stubGlobal("URL", { createObjectURL: () => "blob:audio", revokeObjectURL: (url) => revoked.push(url) });
  return revoked;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const file = new File([new Uint8Array(16)], "talk.m4a", { type: "audio/mp4" });

describe("audioDuration", () => {
  it("reads the duration from the file's metadata and releases the object URL", async () => {
    const revoked = stubUrls();
    vi.stubGlobal("Audio", fakeAudio(3725.4));
    expect(await audioDuration(file)).toBe(3725.4);
    expect(revoked).toEqual(["blob:audio"]);
  });

  it.each([
    ["no duration header (MediaRecorder WebM)", Infinity],
    ["an unreadable file", "error"],
  ])("returns null for %s", async (_case, outcome) => {
    stubUrls();
    vi.stubGlobal("Audio", fakeAudio(outcome));
    expect(await audioDuration(file)).toBeNull();
  });

  it("gives up after the timeout", async () => {
    vi.useFakeTimers();
    const revoked = stubUrls();
    vi.stubGlobal("Audio", fakeAudio("never"));
    const pending = audioDuration(file, { timeoutMs: 500 });
    await vi.advanceTimersByTimeAsync(500);
    expect(await pending).toBeNull();
    expect(revoked).toEqual(["blob:audio"]);
  });

  it("returns null where the browser has no media support", async () => {
    vi.stubGlobal("URL", {});
    expect(await audioDuration(file)).toBeNull();
  });
});
