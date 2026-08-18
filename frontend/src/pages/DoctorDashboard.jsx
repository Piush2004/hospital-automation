import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clearAuth, completeVisit, doctorAppointments, me } from "../api/staffApi.js";

export default function DoctorDashboard() {
  const [profile, setProfile] = useState(null);
  const [appointments, setAppointments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function load() {
    try {
      const [profileData, appts] = await Promise.all([me(), doctorAppointments()]);
      setProfile(profileData);
      setAppointments(appts);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleComplete(event) {
    event.preventDefault();
    if (!selected || !notes.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await completeVisit(selected.id, notes.trim());
      setResult(res);
      setSelected(null);
      setNotes("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearAuth();
    navigate("/staff/login");
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>Doctor dashboard{profile ? ` — ${profile.full_name}` : ""}</h2>
        <button className="link-button" onClick={logout}>
          Log out
        </button>
      </div>

      {error && <p className="mic-error" style={{ textAlign: "left" }}>{error}</p>}

      {result && (
        <div className="notice-banner">
          Visit completed. Report #{result.report_id} generated ({result.sessions_notified} session(s) notified).
        </div>
      )}

      <h3>My confirmed appointments</h3>
      {appointments.length === 0 ? (
        <p className="hint">No confirmed appointments waiting.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Phone</th>
              <th>When</th>
              <th>Reason</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((a) => (
              <tr key={a.id}>
                <td>{a.patient_name}</td>
                <td>{a.patient_phone}</td>
                <td>{new Date(a.slot_start).toLocaleString()}</td>
                <td>{a.reason || "-"}</td>
                <td>
                  <button onClick={() => setSelected(a)}>Complete visit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <form className="complete-form" onSubmit={handleComplete}>
          <h4>
            Complete visit — {selected.patient_name} ({new Date(selected.slot_start).toLocaleString()})
          </h4>
          <textarea
            rows={5}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Visit notes / diagnosis..."
            required
          />
          <div className="form-actions">
            <button type="submit" disabled={busy}>
              {busy ? "Submitting..." : "Mark complete & generate report"}
            </button>
            <button type="button" className="secondary" onClick={() => setSelected(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
