import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useTransient } from "../hooks.js";

function Probe() {
  const [value, show] = useTransient(1000);
  return (
    <button onClick={() => show("copied")}>{value ?? "idle"}</button>
  );
}

afterEach(() => vi.useRealTimers());

describe("useTransient", () => {
  it("resets after the delay and restarts the delay when shown again", async () => {
    vi.useFakeTimers();
    render(<Probe />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("button").textContent).toBe("copied");
    await act(() => vi.advanceTimersByTimeAsync(800));
    fireEvent.click(screen.getByRole("button")); // shown again: a fresh second
    await act(() => vi.advanceTimersByTimeAsync(800));
    expect(screen.getByRole("button").textContent).toBe("copied");
    await act(() => vi.advanceTimersByTimeAsync(300));
    expect(screen.getByRole("button").textContent).toBe("idle");
  });

  it("clears its timer when the component unmounts", () => {
    vi.useFakeTimers();
    const { unmount } = render(<Probe />);
    fireEvent.click(screen.getByRole("button"));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
