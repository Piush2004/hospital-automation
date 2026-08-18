const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const STORAGE_KEY = "staff_auth";

export function getStoredAuth() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveAuth(token, role) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, role }));
}

export function clearAuth() {
  localStorage.removeItem(STORAGE_KEY);
}

export async function login(email, password) {
  const body = new URLSearchParams({ username: email, password });
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || "Login failed");
  }
  const data = await resp.json();
  saveAuth(data.access_token, data.role);
  return data;
}

async function authedFetch(path, options = {}) {
  const auth = getStoredAuth();
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${auth?.token || ""}`,
      ...options.headers,
    },
  });
  if (resp.status === 401) {
    clearAuth();
    throw new Error("Session expired - please log in again.");
  }
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${resp.status})`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const me = () => authedFetch("/auth/me");

export const doctorAppointments = () => authedFetch("/api/doctor/appointments");
export const completeVisit = (appointmentId, notes) =>
  authedFetch(`/api/doctor/appointments/${appointmentId}/complete`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });

export const adminAppointments = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return authedFetch(`/api/admin/appointments${qs ? `?${qs}` : ""}`);
};
export const adminDoctorCalendar = () => authedFetch("/api/admin/doctors/calendar");
export const adminAuditLog = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return authedFetch(`/api/admin/audit-log${qs ? `?${qs}` : ""}`);
};
export const adminEmergencies = () => authedFetch("/api/admin/emergencies");
export const acknowledgeEmergency = (sessionId) =>
  authedFetch(`/api/admin/emergencies/${sessionId}/acknowledge`, { method: "POST" });
