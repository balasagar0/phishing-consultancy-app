// Live updates. One EventSource per open page reads /api/live/stream (Server-Sent Events): new messages, new alerts, triage changes and
// connector states arrive within a second, and pages reload what they show. New alerts also pop up as a toast and, when the person has
// allowed it and the tab is in the background, as a desktop notification that names no person (others may see the screen).
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import { score3 } from "./ui.jsx";

const LiveCtx = createContext({ state: "off", subscribe: () => () => {} });
const TYPES = ["message", "alert", "alert_update", "connector", "hook", "resync"];
const NOTIFY_KEY = "mcpd.notify";

export function notifyWanted() { try { return localStorage.getItem(NOTIFY_KEY) === "1"; } catch { return false; } }
export function setNotifyWanted(v) { try { localStorage.setItem(NOTIFY_KEY, v ? "1" : "0"); } catch { /* storage blocked */ } }

export function LiveProvider({ orgId, children }) {
  const { refresh } = useAuth(); const nav = useNavigate();
  const navRef = useRef(nav); navRef.current = nav;          // navigate() changes with every page; the stream must not reopen for that
  const [state, setState] = useState("connecting");
  const [toasts, setToasts] = useState([]);
  const subs = useRef(new Set());

  const subscribe = useCallback((fn) => { subs.current.add(fn); return () => subs.current.delete(fn); }, []);
  const dismiss = (id) => setToasts((t) => t.filter((x) => x.id !== id));

  useEffect(() => {
    if (!orgId) { setState("off"); return undefined; }
    let es = null; let stopped = false; let timer = null;
    const emit = (type, data) => subs.current.forEach((fn) => { try { fn(type, data); } catch { /* one page's handler must not stop the others */ } });
    const onAlert = (d) => {
      const id = `${d.case_id}-${Date.now()}`;
      setToasts((t) => [...t.slice(-2), { id, ...d }]);
      setTimeout(() => dismiss(id), 12000);
      if (notifyWanted() && typeof Notification !== "undefined" && Notification.permission === "granted" && document.hidden) {
        try {
          const n = new Notification("New phishing alert", { body: `Campaign risk ${score3(d.risk)} over ${(d.channels || []).join(", ") || "—"}. Open the app to triage it.`, tag: `alert-${d.case_id}`, icon: "/icon-192.png" });
          n.onclick = () => { window.focus(); navRef.current(`/app/alerts/${d.case_id}`); n.close(); };
        } catch { /* notifications unavailable */ }
      }
    };
    const open = () => {
      setState("connecting");
      es = new EventSource("/api/live/stream");
      es.addEventListener("hello", () => setState("live"));
      TYPES.forEach((t) => es.addEventListener(t, (e) => {
        let d = {}; try { d = JSON.parse(e.data || "{}"); } catch { /* ignore a malformed line */ }
        emit(t, d); if (t === "alert") onAlert(d);
      }));
      es.addEventListener("end", () => { stopped = true; es.close(); setState("ended"); refresh(); });
      es.onerror = () => {
        if (stopped) return;
        if (es.readyState === EventSource.CLOSED) {           // refused (signed out, no organisation) or the server is down: check, then retry
          setState("offline"); refresh(); timer = setTimeout(open, 5000);
        } else setState("connecting");                          // the browser reconnects by itself
      };
    };
    open();
    return () => { stopped = true; clearTimeout(timer); if (es) es.close(); };
  }, [orgId, refresh]);

  return (
    <LiveCtx.Provider value={{ state, subscribe }}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div className="toast" key={t.id} role="status">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>New alert · risk {score3(t.risk)}</strong>
              <button className="btn small" type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss">✕</button>
            </div>
            <div className="small">{t.recipient} · {(t.channels || []).join(", ") || "no assessed channel"}</div>
            {(t.indicators || []).length > 0 && <div className="small mono muted">{t.indicators.slice(0, 2).join("  ")}</div>}
            <button className="btn small primary" type="button" style={{ marginTop: 6 }} onClick={() => { dismiss(t.id); nav(`/app/alerts/${t.case_id}`); }}>Open alert</button>
          </div>
        ))}
      </div>
    </LiveCtx.Provider>
  );
}

export const useLiveState = () => useContext(LiveCtx).state;

/** Calls fn(type, data) for each live event of the given types while the component is shown. */
export function useLive(types, fn) {
  const { subscribe } = useContext(LiveCtx); const ref = useRef(fn); ref.current = fn;
  const key = types.join(",");
  useEffect(() => subscribe((t, d) => { if (key.split(",").includes(t) || t === "resync") ref.current(t, d); }), [subscribe, key]);
}

/** Reloads (at most once per `wait` ms) when a live event of the given types arrives and `when(data)` is true. */
export function useLiveReload(types, reload, when = () => true, wait = 700) {
  const timer = useRef(null); const w = useRef(when); w.current = when;
  useLive(types, (t, d) => {
    if (t !== "resync" && !w.current(d)) return;
    if (timer.current) return;
    timer.current = setTimeout(() => { timer.current = null; reload(); }, wait);
  });
  useEffect(() => () => clearTimeout(timer.current), []);
}

/** A clock that ticks every `ms`, for "12 s ago" labels. */
export function useNow(ms = 10000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

export function ago(ts, now = Date.now()) {
  if (!ts) return "never";
  const s = Math.max(0, Math.round(now / 1000 - ts));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export function LivePill() {
  const s = useLiveState();
  const [cls, label, title] = {
    live: ["ok", "Live", "New messages and alerts appear as they arrive"],
    connecting: ["warn", "Connecting…", "Connecting to the live stream"],
    offline: ["bad", "Offline", "The live stream is not connected; retrying every few seconds"],
    ended: ["bad", "Signed out", "Your session ended"],
    off: ["", "Not live", "Open an organisation to see live updates"],
  }[s] || ["", s, ""];
  return <span className={`live-pill ${cls}`} title={title} role="status"><span className="dot" aria-hidden="true" />{label}</span>;
}

export const SOURCE = { mailbox: "Mailbox", "sms-hook": "SMS webhook", "mail-hook": "Email webhook", api: "API", web: "Web app", demo: "Demo (hand-written)" };
export const KIND = { imap: "IMAP mailbox", graph: "Microsoft 365 mailbox", demo: "Demo replay" };
export const STATUS_TEXT = { new: "Starting", connecting: "Connecting", live: "Live", polling: "Checking regularly", error: "Problem", paused: "Paused", finished: "Finished" };
