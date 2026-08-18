import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  acknowledgeEmergency,
  adminAppointments,
  adminAuditLog,
  adminDoctorCalendar,
  adminEmergencies,
  clearAuth,
} from "../api/staffApi.js";

const TABS = ["Appointments", "Doctor calendar", "Audit log", "Emergencies"];

export default function AdminDashboard() {
  const [tab, setTab] = useState("Appointments");
  const [appointments, setAppointments] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [auditLog, setAuditLog] = useState([]);
  const [emergencies, setEmergencies] = useState([]);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  async function loadTab(current) {
    setError(null);
    try {
      if (current === "Appointments") setAppointments(await adminAppointments());
      else if (current === "Doctor calendar") setCalendar(await adminDoctorCalendar());
      else if (current === "Audit log") setAuditLog(await adminAuditLog({ limit: 100 }));
      else if (current === "Emergencies") setEmergencies(await adminEmergencies());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadTab(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function handleAcknowledge(sessionId) {
    try {
      await acknowledgeEmergency(sessionId);
      await loadTab("Emergencies");
    } catch (err) {
      setError(err.message);
    }
  }

  function logout() {
    clearAuth();
    navigate("/staff/login");
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>Admin / front desk dashboard</h2>
        <button className="link-button" onClick={logout}>
          Log out
        </button>
      </div>

      <div className="mode-toggle">
        {TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {error && <p className="mic-error" style={{ textAlign: "left" }}>{error}</p>}

      {tab === "Appointments" && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Doctor</th>
              <th>Department</th>
              <th>When</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((a) => (
              <tr key={a.id}>
                <td>{a.patient_name}</td>
                <td>{a.doctor_name}</td>
                <td>{a.department_name}</td>
                <td>{new Date(a.slot_start).toLocaleString()}</td>
                <td>
                  <span className={`status-pill status-${a.status}`}>{a.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "Doctor calendar" && (
        <div className="calendar-list">
          {calendar.map((entry) => (
            <div key={entry.doctor_id} className="calendar-entry">
              <h4>
                {entry.doctor_name} <span className="hint">({entry.department_name})</span>
              </h4>
              {entry.appointments.length === 0 ? (
                <p className="hint">No upcoming appointments.</p>
              ) : (
                <ul>
                  {entry.appointments.map((a) => (
                    <li key={a.id}>
                      {new Date(a.slot_start).toLocaleString()} — {a.patient_name} ({a.status})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "Audit log" && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Entity</th>
            </tr>
          </thead>
          <tbody>
            {auditLog.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.timestamp).toLocaleString()}</td>
                <td>{row.actor}</td>
                <td>{row.action}</td>
                <td>
                  {row.entity_type}
                  {row.entity_id ? ` #${row.entity_id}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "Emergencies" && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Flagged</th>
              <th>Patient</th>
              <th>Channel</th>
              <th>Last message</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {emergencies.map((e) => (
              <tr key={e.session_id} className={e.status === "active" ? "row-alert" : ""}>
                <td>{new Date(e.flagged_at).toLocaleString()}</td>
                <td>
                  {e.patient_name || "Unknown"} ({e.patient_phone})
                </td>
                <td>{e.channel}</td>
                <td>{e.last_message}</td>
                <td>{e.status}</td>
                <td>
                  {e.status === "active" && (
                    <button onClick={() => handleAcknowledge(e.session_id)}>Acknowledge</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
