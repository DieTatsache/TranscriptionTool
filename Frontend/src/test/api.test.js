import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, onSessionExpired, setCsrfToken } from "../api.js";

function jsonResponse(status, body) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(...responses) {
  const fetchMock = vi.fn();
  responses.forEach((r) => fetchMock.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  setCsrfToken(null);
  onSessionExpired(null);
});

describe("CSRF protection", () => {
  it("sends the token only on state-changing requests", async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { user: { id: "u1" }, csrf_token: "csrf-123" }),
      jsonResponse(200, []),
      jsonResponse(204),
    );

    await api.login("a@b.io", "pw");
    await api.listSessions();
    await api.deleteSession("s1");

    const [loginInit, listInit, deleteInit] = fetchMock.mock.calls.map((call) => call[1]);
    expect(loginInit.headers["X-CSRF-Token"]).toBeUndefined(); // no token before sign-in
    expect(listInit.method).toBe("GET");
    expect(listInit.headers["X-CSRF-Token"]).toBeUndefined();
    expect(deleteInit.method).toBe("DELETE");
    expect(deleteInit.headers["X-CSRF-Token"]).toBe("csrf-123");
    expect(deleteInit.credentials).toBe("same-origin");
  });

  it("forgets the token on logout", async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { user: {}, csrf_token: "csrf-123" }),
      jsonResponse(204),
      jsonResponse(401, { error: { code: "not_authenticated", message: "x" } }),
    );
    await api.login("a@b.io", "pw");
    await api.logout();
    await expect(api.updateProfile({ name: "x" })).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock.mock.calls[2][1].headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("encodes path parameters", async () => {
    const fetchMock = mockFetch(jsonResponse(200, {}));
    await api.publicShare("../../admin?x=1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/public/shares/..%2F..%2Fadmin%3Fx%3D1");
  });
});

describe("errors", () => {
  it("exposes the API error code and message", async () => {
    mockFetch(jsonResponse(409, { error: { code: "email_taken", message: "Taken." } }));
    const error = await api.register("N", "a@b.io", "pw").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "email_taken", message: "Taken." });
  });

  it("reports an expired session, but not for sign-in attempts", async () => {
    const expired = vi.fn();
    onSessionExpired(expired);
    mockFetch(
      jsonResponse(401, { error: { code: "invalid_credentials", message: "Invalid" } }),
      jsonResponse(401, { error: { code: "session_expired", message: "Expired" } }),
    );

    await expect(api.login("a@b.io", "wrong")).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(expired).not.toHaveBeenCalled();

    await expect(api.listSessions()).rejects.toMatchObject({ code: "session_expired" });
    expect(expired).toHaveBeenCalledOnce();
  });

  it("maps network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.meta()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("tolerates non-JSON error pages from proxies", async () => {
    mockFetch(new Response("<html>Bad Gateway</html>", { status: 502 }));
    await expect(api.meta()).rejects.toMatchObject({ status: 502, code: "error" });
  });
});

describe("uploadRecording", () => {
  class FakeXHR {
    static last;
    constructor() {
      this.headers = {};
      this.upload = {};
      FakeXHR.last = this;
    }
    open(method, url) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(name, value) {
      this.headers[name] = value;
    }
    send(body) {
      this.body = body;
    }
    abort() {
      this.onabort();
    }
  }

  beforeEach(() => vi.stubGlobal("XMLHttpRequest", FakeXHR));

  it("posts the raw file with CSRF token, query options and progress", async () => {
    setCsrfToken("csrf-9");
    const progress = vi.fn();
    const file = new File(["abc"], "talk.webm", { type: "audio/webm" });

    const pending = api.uploadRecording(file, { language: "de", title: "Week 1", onProgress: progress });
    const xhr = FakeXHR.last;
    xhr.upload.onprogress({ lengthComputable: true, loaded: 1, total: 4 });
    xhr.status = 202;
    xhr.responseText = JSON.stringify({ id: "s1", status: "queued" });
    xhr.onload();

    await expect(pending).resolves.toEqual({ id: "s1", status: "queued" });
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/v1/sessions?title=Week+1&language=de");
    expect(xhr.headers).toMatchObject({ "X-CSRF-Token": "csrf-9", "Content-Type": "audio/webm" });
    expect(xhr.body).toBe(file);
    expect(progress).toHaveBeenCalledWith(0.25);
  });

  it("rejects with the API error", async () => {
    const pending = api.uploadRecording(new File(["x"], "x.bin"));
    const xhr = FakeXHR.last;
    xhr.status = 415;
    xhr.responseText = JSON.stringify({ error: { code: "unsupported_audio", message: "Nope" } });
    xhr.onload();
    await expect(pending).rejects.toMatchObject({ status: 415, code: "unsupported_audio" });
    expect(xhr.headers["Content-Type"]).toBe("application/octet-stream");
  });

  it("can be cancelled", async () => {
    const controller = new AbortController();
    const pending = api.uploadRecording(new File(["x"], "x.webm"), { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
