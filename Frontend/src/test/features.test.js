import { afterEach, describe, expect, it, vi } from "vitest";

// features.js reads the build-time env when it is imported, so each case imports it afresh.
async function loadFeatures() {
  vi.resetModules();
  return import("../features.js");
}

afterEach(() => vi.unstubAllEnvs());

describe("build-time switches", () => {
  it("offer the demo login only in development builds", async () => {
    vi.stubEnv("VITE_DEMO_EMAIL", "demo@example.com");
    vi.stubEnv("VITE_DEMO_PASSWORD", "demo-password");
    vi.stubEnv("DEV", true);
    expect((await loadFeatures()).DEMO_LOGIN).toEqual({ email: "demo@example.com", password: "demo-password" });

    // A production build ignores the credentials even when they are set.
    vi.stubEnv("DEV", false);
    expect((await loadFeatures()).DEMO_LOGIN).toBeNull();
  });

  it("keep the demo login and the video mock off unless configured", async () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_DEMO_EMAIL", undefined);
    vi.stubEnv("VITE_DEMO_PASSWORD", undefined);
    vi.stubEnv("VITE_FEATURE_VIDEO", undefined);
    const { DEMO_LOGIN, FEATURES } = await loadFeatures();
    expect(DEMO_LOGIN).toBeNull();
    expect(FEATURES.video).toBe(false);

    vi.stubEnv("VITE_FEATURE_VIDEO", "true");
    expect((await loadFeatures()).FEATURES.video).toBe(true);
  });
});
