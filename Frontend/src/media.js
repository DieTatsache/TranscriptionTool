// Reads an audio file's duration in the browser before uploading it. Resolves null when the
// browser can't tell (no metadata, e.g. MediaRecorder WebM files, or no media support);
// the server checks the length again either way.
export function audioDuration(file, { timeoutMs = 4000 } = {}) {
  if (typeof URL.createObjectURL !== "function" || typeof Audio === "undefined") {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    const finish = (seconds) => {
      clearTimeout(timer);
      audio.onloadedmetadata = audio.onerror = null;
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(seconds) && seconds > 0 ? seconds : null);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    audio.preload = "metadata";
    audio.onloadedmetadata = () => finish(audio.duration);
    audio.onerror = () => finish(null);
    audio.src = url;
  });
}
