import { Navigate } from "react-router-dom";
import { getStoredAuth } from "../api/staffApi.js";

/**
 * Client-side gate only - purely UX (skip the flash of a page that will
 * immediately 401). The server enforces the real boundary via
 * require_roles() on every request; this component trusts nothing.
 */
export default function ProtectedRoute({ roles, children }) {
  const auth = getStoredAuth();
  if (!auth?.token) return <Navigate to="/staff/login" replace />;
  if (roles && !roles.includes(auth.role)) return <Navigate to="/staff/login" replace />;
  return children;
}
