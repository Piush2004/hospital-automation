import { useEffect, useRef, useState } from "react";

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/chat";
const DEMO_PHONE = "+919810000001";

export default function ChatWidget() {
  const [phone, setPhone] = useState(DEMO_PHONE);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isEmergency, setIsEmergency] = useState(false);
  const wsRef = useRef(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  function connect() {
    const url = `${WS_BASE}?phone=${encodeURIComponent(phone)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMessages((prev) => [...prev, { role: data.role, content: data.content }]);
      if (data.stage === "emergency") setIsEmergency(true);
    };

    wsRef.current = ws;
  }

  function sendMessage() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    wsRef.current.send(text);
    setInput("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter") sendMessage();
  }

  if (!connected) {
    return (
      <div className="chat-shell">
        <div className="identify-panel">
          <label htmlFor="phone">Phone number</label>
          <input
            id="phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+91..."
          />
          <button onClick={connect}>Start chat</button>
          <p className="hint">
            Defaults to a seeded demo patient. Any new number creates a fresh patient record.
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
      <div className="composer">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          autoFocus
        />
        <button onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
}
