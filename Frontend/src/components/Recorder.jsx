import { useEffect, useRef, useState } from "react";
import Icon from "../Icon.jsx";
import { api } from "../api.js";
import { formatDuration } from "../format.js";

// Records with MediaRecorder (all modern browsers) or takes an existing audio file, then
// uploads it for server-side transcription. Nothing is sent to third-party services.

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
const ACCEPT = "audio/*,.webm,.ogg,.oga,.opus,.mp3,.m4a,.mp4,.wav,.flac,.aac";
const BITRATE = 64000; // plenty for speech; ~29 MB per hour

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return null;
  return MIME_TYPES.find((type) => MediaRecorder.isTypeSupported?.(type)) ?? "";
}

function extensionFor(mime) {
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "m4a";
  return "webm";
}

export default function Recorder({ meta, usage, onUploaded, onCancel }) {
  const [phase, setPhase] = useState("idle"); // idle | starting | recording | uploading
  const [paused, setPaused] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [stream, setStream] = useState(null);
  const [language, setLanguage] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [failedFile, setFailedFile] = useState(null); // kept so a lecture is never lost

  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const abortRef = useRef(null);
  const uploadRef = useRef(null);

  const maxSeconds = (meta?.max_audio_minutes ?? 180) * 60;
  const maxMb = meta?.max_upload_mb ?? 200;
  const outOfQuota = usage?.remaining_this_month === 0;
  const busy = phase !== "idle";

  // Release the microphone and cancel uploads when the view closes.
  useEffect(
    () => () => {
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.discard = true;
        recorder.stop();
      }
      abortRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    if (phase !== "recording" || paused) return undefined;
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [phase, paused]);

  // Stop at the server's maximum length instead of recording something unusable.
  useEffect(() => {
    const recorder = recorderRef.current;
    if (phase === "recording" && seconds >= maxSeconds && recorder?.state !== "inactive") recorder?.stop();
  }, [phase, seconds, maxSeconds]);

  useEffect(() => {
    if (phase !== "recording" && phase !== "uploading") return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);

  const upload = async (file) => {
    if (file.size > maxMb * 1024 * 1024) {
      setError(`The file is larger than ${maxMb} MB.`);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase("uploading");
    setProgress(0);
    setError(null);
    try {
      const session = await api.uploadRecording(file, {
        language: language || undefined,
        onProgress: setProgress,
        signal: controller.signal,
      });
      setFailedFile(null);
      onUploaded(session);
    } catch (err) {
      if (err.name === "AbortError") return;
      setPhase("idle");
      setFailedFile(file);
      setError(uploadErrorMessage(err));
    }
  };

  // MediaRecorder's onstop fires later; it always calls the latest upload function.
  useEffect(() => {
    uploadRef.current = upload;
  });

  const start = async () => {
    setError(null);
    setFailedFile(null);
    const mimeType = pickMimeType();
    if (mimeType === null || !navigator.mediaDevices?.getUserMedia) {
      setError("Recording is not supported in this browser. You can upload an audio file instead.");
      return;
    }
    setPhase("starting");
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(media, {
        ...(mimeType ? { mimeType } : {}),
        audioBitsPerSecond: BITRATE,
      });
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        media.getTracks().forEach((track) => track.stop());
        setStream(null);
        const type = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        if (recorder.discard) return;
        const name = `recording-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.${extensionFor(type)}`;
        uploadRef.current(new File([blob], name, { type }));
      };
      recorderRef.current = recorder;
      recorder.start(1000); // regular chunks: nothing big is lost if the tab crashes mid-way
      setStream(media);
      setSeconds(0);
      setPaused(false);
      setPhase("recording");
    } catch (err) {
      setPhase("idle");
      setError(
        err?.name === "NotAllowedError"
          ? "Microphone access was denied. Allow it in the browser settings, or upload a file instead."
          : `Could not start recording: ${err?.message ?? err}`,
      );
    }
  };

  const togglePause = () => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.pause();
      setPaused(true);
    } else if (recorder?.state === "paused") {
      recorder.resume();
      setPaused(false);
    }
  };

  const stop = () => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  };

  const cancel = () => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.discard = true;
      recorder.stop();
    }
    abortRef.current?.abort();
    onCancel();
  };

  const onFileChosen = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) upload(file);
  };

  const downloadFailed = () => {
    const url = URL.createObjectURL(failedFile);
    const link = document.createElement("a");
    link.href = url;
    link.download = failedFile.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  const languageName = meta?.languages?.find((l) => l.code === language)?.name;

  return (
    <div className="recorder fade-up">
      <div className="rec-panel">
        {phase === "uploading" ? (
          <div className="upload-progress" aria-live="polite">
            <div className="rec-status">
              <span className="proc-spinner" /> Uploading recording…
            </div>
            <div className="proc-bar">
              <div className="proc-bar-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <span className="upload-percent">{Math.round(progress * 100)}%</span>
            <button className="btn btn-ghost" onClick={cancel}>
              Cancel
            </button>
          </div>
        ) : phase === "idle" ? (
          <>
            <div className="rec-status">
              <span className="rec-dot paused" /> Ready to record
            </div>
            <div className="rec-timer">00:00</div>
            <label className="rec-language">
              <span>Spoken language</span>
              <select className="field-input" value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="">Detect automatically</option>
                {meta?.languages?.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="rec-controls">
              <button className="btn btn-ghost" onClick={onCancel}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={start} disabled={outOfQuota}>
                <Icon name="mic" size={16} /> Start recording
              </button>
            </div>
            <p className="rec-hint">
              Your browser will ask for microphone access. Maximum length {formatDuration(maxSeconds)}.
            </p>
          </>
        ) : (
          <>
            <div className="rec-status">
              <span className={"rec-dot" + (paused ? " paused" : "") + (phase === "starting" ? " waiting" : "")} />
              {phase === "starting" ? "Requesting microphone…" : paused ? "Paused" : "Recording"}
            </div>
            <div className="rec-timer">
              {mm}:{ss}
            </div>
            <Waveform active={phase === "recording" && !paused} stream={stream} />
            <div className="rec-controls">
              <button className="btn btn-ghost" onClick={cancel}>
                Discard
              </button>
              <button className="btn btn-secondary" disabled={phase !== "recording"} onClick={togglePause}>
                {paused ? "Resume" : "Pause"}
              </button>
              <button className="btn btn-primary" disabled={phase !== "recording"} onClick={stop}>
                <Icon name="check" size={16} /> Stop & analyze
              </button>
            </div>
          </>
        )}

        {outOfQuota && phase === "idle" && (
          <div className="banner warn">
            <Icon name="alert" size={16} />
            <span>You have used all sessions of your plan this month.</span>
          </div>
        )}
        {error && (
          <div className="banner error" role="alert">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        )}
        {failedFile && phase === "idle" && (
          <div className="rec-controls">
            <button className="btn btn-secondary btn-sm" onClick={() => upload(failedFile)}>
              <Icon name="refresh" size={14} /> Retry upload
            </button>
            <button className="btn btn-ghost btn-sm" onClick={downloadFailed}>
              <Icon name="arrow" size={14} /> Save recording
            </button>
          </div>
        )}
      </div>

      <aside className="rec-feed">
        <div className="rec-feed-head">
          <Icon name="upload" size={16} /> Upload a recording instead
        </div>
        <div className="rec-feed-body">
          <label className={"dropzone" + (busy || outOfQuota ? " disabled" : "")}>
            <input type="file" accept={ACCEPT} onChange={onFileChosen} disabled={busy || outOfQuota} hidden />
            <Icon name="upload" size={24} />
            <strong>Choose an audio file</strong>
            <span>
              WebM, Ogg, MP3, M4A, WAV, FLAC or AAC · up to {maxMb} MB · at most {formatDuration(maxSeconds)}
            </span>
            <span>Language: {languageName ?? "detected automatically"}</span>
          </label>
          <div className="rec-note">
            <Icon name="spark" size={15} />
            <p>
              The recording is transcribed on Sonora&apos;s own servers once it is uploaded — it is not sent to
              third-party speech services, and the audio is deleted after transcription.
            </p>
          </div>
        </div>
      </aside>
    </div>
  );
}

function uploadErrorMessage(err) {
  switch (err.code) {
    case "unsupported_audio":
    case "unsupported_media_type":
      return "This file type is not supported. Use WebM, Ogg, MP3, M4A, WAV, FLAC or AAC.";
    case "payload_too_large":
      return "The file is too large.";
    case "audio_too_short":
      return "The recording is empty or too short.";
    case "rate_limited":
      return "Too many uploads in a short time. Please wait a moment and try again.";
    default:
      return err.message || "The upload failed.";
  }
}

// Live level meter fed by the microphone stream (AnalyserNode).
function Waveform({ active, stream }) {
  const [bars, setBars] = useState(() => Array.from({ length: 48 }, () => 0.15));

  useEffect(() => {
    if (!active || !stream) return undefined;
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 128;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let frame;
    const tick = () => {
      analyser.getByteFrequencyData(data);
      setBars(Array.from({ length: 48 }, (_, i) => Math.max(0.08, data[Math.floor((i / 48) * data.length)] / 255)));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      audioCtx.close();
    };
  }, [active, stream]);

  return (
    <div className={"waveform" + (active ? "" : " idle")}>
      {bars.map((h, i) => (
        <span key={i} style={{ height: `${(active ? h : 0.15) * 100}%` }} />
      ))}
    </div>
  );
}
