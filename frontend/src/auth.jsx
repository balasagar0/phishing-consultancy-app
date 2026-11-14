import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, setCsrf } from "./api.js";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);

  const accept = (m) => { const v = m && m.signed_in ? m : null; setCsrf(v ? v.csrf : ""); setMe(v); return v; };
  const refresh = useCallback(async () => {
    try { return accept(await api("/api/auth/me")); } catch { return accept(null); } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email, password) => accept(await api("/api/auth/login", { method: "POST", body: { email, password } }));
  const logout = async () => { try { await api("/api/auth/logout", { method: "POST" }); } finally { accept(null); } };
  const switchOrg = async (org_id) => accept(await api("/api/auth/switch-org", { method: "POST", body: { org_id } }));

  return <AuthCtx.Provider value={{ me, loading, login, logout, refresh, switchOrg }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
const RANK = { viewer: 0, analyst: 1, admin: 2, superadmin: 3 };
export const can = (me, role) => !!me && RANK[me.user.role] >= RANK[role];
