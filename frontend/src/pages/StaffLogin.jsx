import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/staffApi.js";

export default function StaffLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const data = await login(email, password);
      navigate(data.role === "doctor" ? "/staff/doctor" : "/staff/admin");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat-shell">
      <form className="identify-panel" onSubmit={handleSubmit}>
        <h2 style={{ margin: "0 0 4px" }}>Staff login</h2>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="mic-error" style={{ padding: 0 }}>{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in..." : "Sign in"}
        </button>
        <p className="hint">
          Doctor, front desk, or admin accounts only. Seeded demo accounts (local dev): any
          <code> @clinic.local</code> address from <code>seed_demo_data.py</code>, shared dev
          password printed when you ran that script.
        </p>
      </form>
    </div>
  );
}
