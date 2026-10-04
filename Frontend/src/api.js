//API running on same origin. Session is in HttpOnly Cookie and CSRF Token only in Memory

const BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let csrfToken = null;
let sessionExpiredHandler = null;

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function setCsrfToken(token) {
  csrfToken = token;
}

// Function when authenticated request fails with 401
export function onSessionExpired(handler) {
  sessionExpiredHandler = handler;
}

async function request(path, { method = "GET", body, signal, authProbe = false } = {}) {
  const headers = { Accept: "application/json" };
  const init = { method, headers, credentials: "same-origin", signal };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (UNSAFE.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response;
  try {
    response = await fetch(BASE + path, init);
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "The server could not be reached.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = toApiError(response.status, data);
    if (response.status === 401 && !authProbe) sessionExpiredHandler?.(error);
    throw error;
  }
  return data;
}

function toApiError(status, data) {
  const error = data?.error ?? {};
  return new ApiError(
    status,
    error.code ?? "error",
    error.message ?? `Request failed (${status}).`,
    error.details,
  );
}

const id = (value) => encodeURIComponent(value);

function remember(auth) {
  setCsrfToken(auth.csrf_token);
  return auth.user;
}

// XMLHttpRequest upload (cause fetch cannot report upload progress).
function uploadRecording(file, { title, language, onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams();
    if (title) params.set("title", title);
    if (language) params.set("language", language);
    const query = params.toString();

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/sessions${query ? `?${query}` : ""}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    if (csrfToken) xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // no JSON error page from a proxy
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      const error = toApiError(xhr.status, data);
      if (xhr.status === 401) sessionExpiredHandler?.(error);
      reject(error);
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", "The upload failed. Check your connection."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

export const api = {
  // Returns config the UI needs on startup (feature flags, upload limits, supported languages)
  meta: () => request("/meta"),

  // Checks if current cookie session is valid
  me: async () => remember(await request("/auth/me", { authProbe: true })),
  // Login and store the CSRF token for all future requests
  login: async (email, password) =>
    remember(await request("/auth/login", { method: "POST", body: { email, password }, authProbe: true })),
  // Registers a new account, plan included
  register: async (name, email, password, plan) =>
    remember(
      await request("/auth/register", { method: "POST", body: { name, email, password, plan }, authProbe: true }),
    ),
  // Clears the CSRF token
  logout: async () => {
    try {
      await request("/auth/logout", { method: "POST", authProbe: true });
    } finally {
      setCsrfToken(null);
    }
  },
  // As name Says, updates Profile or password
  updateProfile: (changes) => request("/me", { method: "PATCH", body: changes }),
  changePassword: (currentPassword, newPassword) =>
    request("/me/password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  // Also clears the CSRF token so no authenticated requests can be made afterwards.
  deleteAccount: async (password) => {
    await request("/me/delete", { method: "POST", body: { password } });
    setCsrfToken(null);
  },
  // Returns plan, session count and how many sessions left
  usage: () => request("/me/usage"),
  stats: () => request("/me/stats"),
  activity: (limit = 10) => request(`/me/activity?limit=${limit}`),

  listSessions: () => request("/sessions"),
  uploadRecording,
  getSession: (sessionId, signal) => request(`/sessions/${id(sessionId)}`, { signal }),
  deleteSession: (sessionId) => request(`/sessions/${id(sessionId)}`, { method: "DELETE" }),
  // requeues the session for processing
  retrySession: (sessionId) => request(`/sessions/${id(sessionId)}/retry`, { method: "POST" }),
  // Sends the users answers to server for grading
  checkQuiz: (sessionId, answers) =>
    request(`/sessions/${id(sessionId)}/quiz/check`, { method: "POST", body: { answers } }),

  chatHistory: (sessionId) => request(`/sessions/${id(sessionId)}/chat`),
  askChat: (sessionId, message) =>
    request(`/sessions/${id(sessionId)}/chat`, { method: "POST", body: { message } }),

  // Creates scoped share links
  listShares: (sessionId) => request(`/sessions/${id(sessionId)}/shares`),
  createShare: (sessionId, tabs, expiresInDays) =>
    request(`/sessions/${id(sessionId)}/shares`, {
      method: "POST",
      body: { tabs, expires_in_days: expiresInDays },
    }),
  revokeShare: (sessionId, shareId) =>
    request(`/sessions/${id(sessionId)}/shares/${id(shareId)}`, { method: "DELETE" }),

  // Public endpoints => no auth cookie needed
  publicShare: (token) => request(`/public/shares/${id(token)}`, { authProbe: true }),
  checkSharedQuiz: (token, answers) =>
    request(`/public/shares/${id(token)}/quiz/check`, { method: "POST", body: { answers }, authProbe: true }),
};
