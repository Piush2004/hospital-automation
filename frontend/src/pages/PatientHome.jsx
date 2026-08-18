import { useState } from "react";
import { Link } from "react-router-dom";
import ChatWidget from "../ChatWidget.jsx";
import VoiceWidget from "../VoiceWidget.jsx";

export default function PatientHome() {
  const [mode, setMode] = useState("chat");

  return (
    <div className="page">
      <header className="page-header">
        <h1>Hospital Automation</h1>
        <p>Local demo — triage, doctor assignment, and booking, end to end.</p>
        <div className="mode-toggle">
          <button className={mode === "chat" ? "active" : ""} onClick={() => setMode("chat")}>
            Text chat
          </button>
          <button className={mode === "voice" ? "active" : ""} onClick={() => setMode("voice")}>
            Voice
          </button>
        </div>
      </header>
      {mode === "chat" ? <ChatWidget /> : <VoiceWidget />}
      <p className="staff-link">
        <Link to="/staff/login">Staff login →</Link>
      </p>
    </div>
  );
}
