import { useEffect, useRef, useState } from "react";

const WS_BASE = import.meta.env.VITE_VOICE_WS_URL || "ws://localhost:8000/ws/voice";
const DEMO_PHONE = "+919810000001";

export default function VoiceWidget() {
  const [phone, setPhone] = useState(DEMO_PHONE);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [isEmergency, setIsEmergency] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [micError, setMicError] = useState(null);

  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const pendingHasAudioRef = useRef(false);
  const audioRef = useRef(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  function playAudio(arrayBuffer) {
    const blob = new Blob([arrayBuffer], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.play().catch(() => {
        // Autoplay can be blocked before the first user gesture - the
        // "Hold to talk" press that got us here counts as one, but some
        // browsers are still stricter. Not fatal: the transcript still
        // shows the reply text.
      });
    }
  }

  function connect() {
    const url = `${WS_BASE}?phone=${encodeURIComponent(phone)}`;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    // Server sends one JSON text frame per turn, immediately followed by
    // a binary frame with the WAV audio when has_audio is true. Frames
    // arrive in order on the same connection, so pendingHasAudioRef just
    // tracks "the next binary frame belongs to the message I just showed."
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        const data = JSON.parse(event.data);
        setBusy(false);
        setMessages((prev) => {
          const next = [...prev];
          if (data.heard) next.push({ role: "user", content: data.heard });
          next.push({ role: "assistant", content: data.content });
          return next;
        });
        if (data.stage === "emergency") setIsEmergency(true);
        pendingHasAudioRef.current = Boolean(data.has_audio);
      } else if (pendingHasAudioRef.current) {
        playAudio(event.data);
        pendingHasAudioRef.current = false;
      }
    };

    wsRef.current = ws;
  }

  async function startRecording() {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || busy || isRecording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        blob.arrayBuffer().then((buffer) => {
          if (buffer.byteLength === 0) return;
          setBusy(true);
          wsRef.current.send(buffer);
        });
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setMicError(null);
    } catch (err) {
      setMicError(`Couldn't access the microphone: ${err.message}`);
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }

  if (!connected) {
    return (
      <div className="chat-shell">
        <div className="identify-panel">
          <label htmlFor="voice-phone">Phone number</label>
          <input
            id="voice-phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+91..."
          />
          <button onClick={connect}>Start voice call</button>
          <p className="hint">
            Browser-based voice demo (not a real phone call) — needs microphone access. Hold the
            button below to speak, release to send.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-shell">
      {isEmergency && (
        <div className="emergency-banner">
          Emergency language detected — this conversation has been flagged for staff attention.
        </div>
      )}
      <div className="chat-log">
        {messages.map((msg, i) => (
          <div key={i} className={`bubble ${msg.role}`}>
            {msg.content}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
      {micError && <p className="mic-error">{micError}</p>}
      <div className="voice-controls">
        <button
          className={`mic-button ${isRecording ? "recording" : ""}`}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={() => isRecording && stopRecording()}
          onTouchStart={(event) => {
            event.preventDefault();
            startRecording();
          }}
          onTouchEnd={(event) => {
            event.preventDefault();
            stopRecording();
          }}
          disabled={busy}
        >
          {busy ? "Thinking..." : isRecording ? "Listening... release to send" : "Hold to talk"}
        </button>
      </div>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} />
    </div>
  );
}
