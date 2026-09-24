// Display helpers. The API sends raw values (seconds, ISO timestamps); formatting
// happens here so the UI stays consistent.

export const PROCESSING_STATUSES = ["queued", "transcribing", "generating"];

export function isProcessing(session) {
  return PROCESSING_STATUSES.includes(session?.status);
}

// 250 -> "04:10", 3880 -> "1:04:40"
export function formatTimestamp(seconds) {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

// 2520 -> "42 min", 4080 -> "1h 08m", 35 -> "35s"
export function formatDuration(seconds) {
  if (seconds == null) return "–";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m} min`;
  return `${total}s`;
}

export function formatDate(iso, locale = "en-US") {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" });
}

export function initials(name) {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function formatPrice(cents) {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(
    cents / 100,
  );
}

// Splits "**bold** text" into React-safe segments (no HTML injection possible).
export function boldSegments(text) {
  return (text ?? "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? { bold: true, text: part.slice(2, -2) }
      : { bold: false, text: part },
  );
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false; // clipboard permission denied / insecure context
  }
}
