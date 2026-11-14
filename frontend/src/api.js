// The only way the frontend talks to the server. Same origin, session cookie, and the CSRF token on every change.
let csrf = "";
export function setCsrf(t) { csrf = t || ""; }

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function detailOf(d) {
  if (!d) return "";
  if (typeof d === "string") return d;
  if (typeof d.detail === "string") return d.detail;
  if (Array.isArray(d.detail)) return d.detail.map((x) => `${(x.loc || []).slice(1).join(".") || "input"}: ${x.msg}`).join("; ");
  return "";
}

export async function api(path, { method = "GET", body, raw = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  let r;
  try {
    r = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  if (raw) {
    if (!r.ok) { let d = null; try { d = await r.json(); } catch { /* not JSON */ } throw new ApiError(r.status, detailOf(d) || r.statusText); }
    return r;
  }
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) throw new ApiError(r.status, detailOf(data) || `${r.status} ${r.statusText}`);
  return data;
}

export async function download(path, fallbackName) {
  const r = await api(path, { raw: true });
  const cd = r.headers.get("content-disposition") || "";
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || fallbackName;
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
