import { describe, expect, it } from "vitest";
import { boldSegments, formatDuration, formatPrice, formatTimestamp, initials, isProcessing } from "../format.js";

describe("formatting", () => {
  it.each([
    [0, "00:00"],
    [250, "04:10"],
    [3880, "1:04:40"],
    [null, "00:00"],
  ])("timestamp %s -> %s", (seconds, text) => {
    expect(formatTimestamp(seconds)).toBe(text);
  });

  it.each([
    [35, "35s"],
    [2520, "42 min"],
    [4080, "1h 08m"],
    [null, "–"],
  ])("duration %s -> %s", (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });

  it("initials", () => {
    expect(initials("Marie Tanner")).toBe("MT");
    expect(initials("  cher ")).toBe("C");
    expect(initials("")).toBe("?");
  });

  it("price", () => {
    expect(formatPrice(4900).replace(/\s/g, " ")).toBe("49 €");
  });

  it("processing states", () => {
    expect(isProcessing({ status: "transcribing" })).toBe(true);
    expect(isProcessing({ status: "ready" })).toBe(false);
    expect(isProcessing(null)).toBe(false);
  });
});

describe("boldSegments", () => {
  it("splits **bold** markers", () => {
    expect(boldSegments("Wait a **full breath** now")).toEqual([
      { bold: false, text: "Wait a " },
      { bold: true, text: "full breath" },
      { bold: false, text: " now" },
    ]);
  });

  it("keeps markup as plain text (rendered by React, never as HTML)", () => {
    const segments = boldSegments('<img src=x onerror="alert(1)"> **<b>x</b>**');
    expect(segments[0]).toEqual({ bold: false, text: '<img src=x onerror="alert(1)"> ' });
    expect(segments[1]).toEqual({ bold: true, text: "<b>x</b>" });
  });

  it("handles empty and unmatched markers", () => {
    expect(boldSegments(null)).toEqual([]);
    expect(boldSegments("a ** b")).toEqual([{ bold: false, text: "a ** b" }]);
  });
});
