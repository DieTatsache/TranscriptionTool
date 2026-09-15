import { useEffect, useRef, useState } from "react";
import Icon from "../Icon.jsx";

// Real microphone recording using MediaRecorder (for waveform/timer)
// and Web Speech API (for live transcript).
export default function Recorder({ onStop, onCancel }) {
  const [seconds, setSeconds] = useState(0);
  const [paused, setPaused] = useState(false);
  const [lines, setLines] = useState([]);
  const [micError, setMicError] = useState(null);
  const [micReady, setMicReady] = useState(false);

  const feedRef = useRef(null);
  const streamRef = useRef(null);
  const recognitionRef = useRef(null);
  const entriesRef = useRef([]); // { text, offsetSeconds, isFinal }
  const interimRef = useRef(""); // current interim result
  const startTimeRef = useRef(null);

  // Request mic and set up speech recognition
  useEffect(() => {
    let stopped = false;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setMicError("Web Speech API not supported in this browser. Please use Chrome.");
      return;
    }

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        startTimeRef.current = Date.now();
        setMicReady(true);

        // Set up speech recognition
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "de-DE"; // German first; user can speak either language

        recognition.onresult = (event) => {
          let interim = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
              const text = result[0].transcript.trim();
              if (text) {
                const offsetSeconds = Math.round((Date.now() - startTimeRef.current) / 1000);
                const entry = { text, offsetSeconds, isFinal: true };
                entriesRef.current = [...entriesRef.current, entry];
                setLines((prev) => [
                  ...prev,
                  { t: formatTime(offsetSeconds), speaker: "Speaker", text },
                ]);
              }
            } else {
              interim += result[0].transcript;
            }
          }
          interimRef.current = interim;
        };

        recognition.onerror = (e) => {
          if (e.error !== "no-speech" && e.error !== "aborted") {
            setMicError(`Speech recognition error: ${e.error}`);
          }
        };

        // Restart recognition on end (it stops after ~1 min silence on some browsers)
        recognition.onend = () => {
          if (!stopped && !paused) {
            try { recognition.start(); } catch (_) {}
          }
        };

        recognitionRef.current = recognition;
        try { recognition.start(); } catch (_) {}
      })
      .catch((err) => {
        if (!stopped) setMicError(`Microphone access denied: ${err.message}`);
      });

    return () => {
      stopped = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      recognitionRef.current?.stop();
      recognitionRef.current = null;
    };
  }, []);

  // Timer
  useEffect(() => {
    if (paused || !micReady) return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [paused, micReady]);

  // Pause/resume recognition
  useEffect(() => {
    if (!recognitionRef.current) return;
    if (paused) {
      recognitionRef.current.stop();
    } else {
      try { recognitionRef.current.start(); } catch (_) {}
    }
  }, [paused]);

  // Scroll feed to bottom
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  const handleStop = () => {
    recognitionRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    onStop(seconds, entriesRef.current);
  };

  const handleCancel = () => {
    recognitionRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    onCancel();
  };

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div className="recorder fade-up">
      <div className="rec-panel">
        {micError ? (
          <div className="rec-error">
            <Icon name="close" size={20} />
            <p>{micError}</p>
            <button className="btn btn-ghost" onClick={handleCancel}>Cancel</button>
          </div>
        ) : (
          <>
            <div className="rec-status">
              <span className={"rec-dot" + (paused ? " paused" : "") + (!micReady ? " waiting" : "")} />
              {!micReady ? "Requesting microphone…" : paused ? "Paused" : "Recording"}
            </div>

            <div className="rec-timer">{mm}:{ss}</div>

            <Waveform active={micReady && !paused} stream={streamRef.current} />

            <div className="rec-controls">
              <button className="btn btn-ghost" onClick={handleCancel}>Cancel</button>
              <button
                className="btn btn-secondary"
                disabled={!micReady}
                onClick={() => setPaused((p) => !p)}
              >
                {paused ? "Resume" : "Pause"}
              </button>
              <button
                className="btn btn-primary"
                disabled={!micReady}
                onClick={handleStop}
              >
                <Icon name="check" size={16} /> Stop & analyze
              </button>
            </div>
          </>
        )}
      </div>

      <div className="rec-feed">
        <div className="rec-feed-head">
          <Icon name="transcript" size={16} /> Live transcript
          {!micReady && !micError && (
            <span className="rec-feed-hint"> — waiting for mic permission</span>
          )}
        </div>
        <div className="rec-feed-body" ref={feedRef}>
          {lines.length === 0 && micReady && (
            <div className="rec-feed-empty">Listening… start speaking</div>
          )}
          {lines.map((l, i) => (
            <div className="feed-line fade-up" key={i}>
              <span className="feed-time">{l.t}</span>
              <div>
                <span className="feed-speaker speaker">{l.speaker}</span>
                <p>{l.text}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Waveform that reads from a real MediaStream via AnalyserNode
function Waveform({ active, stream }) {
  const [bars, setBars] = useState(() => Array.from({ length: 48 }, () => 0.15));
  const analyserRef = useRef(null);
  const frameRef = useRef(null);
  const ctxRef = useRef(null);

  useEffect(() => {
    if (!active || !stream) {
      setBars(Array.from({ length: 48 }, () => 0.15));
      return;
    }

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    ctxRef.current = audioCtx;
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 128;
    const source = audioCtx.createMediaStreamSource(stream);
    source.connect(analyser);
    analyserRef.current = analyser;

    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteFrequencyData(data);
      // Map 64 frequency bins to 48 bars
      const newBars = Array.from({ length: 48 }, (_, i) => {
        const bin = Math.floor((i / 48) * data.length);
        return Math.max(0.08, data[bin] / 255);
      });
      setBars(newBars);
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameRef.current);
      audioCtx.close();
    };
  }, [active, stream]);

  return (
    <div className={"waveform" + (active ? "" : " idle")}>
      {bars.map((h, i) => (
        <span key={i} style={{ height: `${h * 100}%` }} />
      ))}
    </div>
  );
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
