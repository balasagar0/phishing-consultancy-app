import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { can, useAuth } from "../auth.jsx";
import { KIND, SOURCE, STATUS_TEXT, ago, notifyWanted, setNotifyWanted, useLive, useLiveState, useNow } from "../live.jsx";
import { ALERT_LINE, Empty, ErrorBox, Loading, RiskBadge, Tiles, fmtTime, score3, useLoad } from "../ui.jsx";
import { PageHead } from "./Shell.jsx";

const CHANNELS = ["all", "email", "sms", "url", "call"];
const KEEP = 300;

export function StatusDot({ status }) {
  return <span className="row" style={{ gap: 6, display: "inline-flex" }}><span className={`status-dot ${status}`} aria-hidden="true" />{STATUS_TEXT[status] || status}</span>;
}

function NotifyToggle() {
  const supported = typeof Notification !== "undefined";
  const [on, setOn] = useState(supported && notifyWanted() && Notification.permission === "granted");
  const [msg, setMsg] = useState("");
  if (!supported) return null;
  const toggle = async () => {
    if (on) { setNotifyWanted(false); setOn(false); return; }
    const p = Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
    if (p === "granted") { setNotifyWanted(true); setOn(true); setMsg(""); } else setMsg("The browser blocks notifications for this site; allow them in its site settings.");
  };
  return (
    <span className="row small">
      <button className="btn small" type="button" onClick={toggle} aria-pressed={on}>{on ? "Desktop notifications: on" : "Desktop notifications: off"}</button>
      {msg && <span className="muted">{msg}</span>}
    </span>
  );
}

export function LiveFeed() {
  const { me } = useAuth(); const nav = useNavigate(); const now = useNow(5000); const live = useLiveState(); const admin = can(me, "admin");
  const recent = useLoad(() => api("/api/live/recent?limit=200"), [me.org?.id]);
  const src = useLoad(() => api("/api/live/sources"), [me.org?.id]);
  const [rows, setRows] = useState([]); const [conns, setConns] = useState([]); const [fresh, setFresh] = useState(() => new Set());
  const [hold, setHold] = useState(false); const [pending, setPending] = useState([]);
  const [chan, setChan] = useState("all"); const [onlyAlert, setOnlyAlert] = useState(false); const [err, setErr] = useState(null);
  const holdRef = useRef(hold); holdRef.current = hold;
  const seenLive = useRef(false);

  useEffect(() => {                                   // merge: a message pushed while the list was loading must not be lost
    if (recent.data) setRows((r) => { const m = new Map([...recent.data, ...r].map((x) => [x.id, x])); return [...m.values()].sort((a, b) => b.id - a.id).slice(0, KEEP); });
  }, [recent.data]);
  useEffect(() => { if (src.data) setConns(src.data.connectors); }, [src.data]);
  useEffect(() => {                                   // after a reconnection, catch up on what arrived while the stream was down
    if (live !== "live") return;
    if (seenLive.current) { recent.reload(); src.reload(); }
    seenLive.current = true;
  }, [live]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = (items) => {
    setRows((r) => [...items, ...r.filter((x) => !items.some((y) => y.id === x.id))].slice(0, KEEP));
    setFresh((f) => { const n = new Set(f); items.forEach((i) => n.add(i.id)); return n; });
    setTimeout(() => setFresh((f) => { const n = new Set(f); items.forEach((i) => n.delete(i.id)); return n; }), 2600);
  };
  useLive(["message", "connector"], (t, d) => {
    if (t === "resync") { recent.reload(); src.reload(); return; }
    if (t === "connector") { setConns((cs) => (cs.some((c) => c.id === d.id) ? cs.map((c) => (c.id === d.id ? { ...c, ...d } : c)) : [...cs, d])); return; }
    if (holdRef.current) setPending((p) => [d, ...p].slice(0, KEEP)); else add([d]);
  });

  const demo = conns.find((c) => c.kind === "demo");
  const playDemo = async (on) => {
    setErr(null);
    try { const c = await api(`/api/admin/connectors/${demo.id}`, { method: "PATCH", body: { active: on } }); setConns((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x))); }
    catch (e) { setErr(e); }
  };
  const resume = () => { setHold(false); if (pending.length) add([...pending]); setPending([]); };

  const shown = rows.filter((m) => (chan === "all" || m.channel === chan) && (!onlyAlert || (m.score ?? 0) >= ALERT_LINE || (m.campaign_risk ?? 0) >= ALERT_LINE));
  const lastHour = rows.filter((m) => m.received_at >= now / 1000 - 3600).length;
  const running = conns.filter((c) => ["live", "polling"].includes(c.status)).length;
  const keys = src.data?.api_keys || [];

  return (
    <>
      <PageHead title="Live feed" actions={<NotifyToggle />}>
        Every message the service records, as it arrives from your mailboxes, SMS gateway and other sources. Message text is never shown here.
      </PageHead>
      {live !== "live" && live !== "off" && <div className="note warn" style={{ marginBottom: 12 }}>The live connection is {live === "connecting" ? "being made" : "down"}. The feed catches up when it reconnects.</div>}
      <ErrorBox error={err || src.error} />
      <Tiles items={[["Messages in the last hour", lastHour >= 200 ? "200+" : lastHour], ["Last message", rows[0] ? ago(rows[0].received_at, now) : "none yet"],
        ["Sources reading now", `${running} of ${conns.length}`], ["API keys in use", keys.filter((k) => k.last_used_at).length]]} />

      <div className="source-grid" style={{ marginTop: 16 }}>
        {conns.map((c) => (
          <div className="card" key={c.id}>
            <div className="row" style={{ justifyContent: "space-between" }}><strong>{c.name}</strong><StatusDot status={c.status} /></div>
            <div className="small muted">{KIND[c.kind] || c.kind}</div>
            <p className="small" style={{ margin: "6px 0" }}>{c.detail}</p>
            <div className="small muted">{c.n_messages} message(s) · {c.n_alerts} alert(s){c.n_skipped ? ` · ${c.n_skipped} skipped` : ""} · last message {ago(c.last_message_at, now)}</div>
            {c.kind === "demo" && admin && (
              <div className="row" style={{ marginTop: 8 }}>
                {c.active ? <button className="btn small" type="button" onClick={() => playDemo(false)}>Stop the demo</button>
                  : <button className="btn small primary" type="button" onClick={() => playDemo(true)}>Play the demo feed</button>}
                <span className="small muted">Hand-written demo messages, not real ones.</span>
              </div>
            )}
          </div>
        ))}
        {!conns.length && (
          <div className="card">
            <strong>No mailbox is connected yet.</strong>
            <p className="small" style={{ margin: "6px 0 0" }}>
              {admin ? <>Connect a mailbox, a Microsoft 365 inbox or an SMS gateway under <Link to="/app/connectors">Connectors</Link>; messages then arrive here by themselves.</>
                : "Ask your organisation's admin to connect a mailbox or an SMS gateway; messages then arrive here by themselves."}
              {keys.length > 0 && ` ${keys.length} API key(s) can also send messages in.`}
            </p>
          </div>
        )}
      </div>

      <div className="card table-wrap" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div className="row" role="group" aria-label="Channel">
            {CHANNELS.map((c) => <button key={c} type="button" className={`btn small ${chan === c ? "primary" : ""}`} aria-pressed={chan === c} onClick={() => setChan(c)}>{c === "all" ? "All" : c.toUpperCase()}</button>)}
            <label className="check" style={{ margin: 0 }}><input type="checkbox" checked={onlyAlert} onChange={(e) => setOnlyAlert(e.target.checked)} /> At or above the alert line</label>
          </div>
          {hold ? <button className="btn small primary" type="button" onClick={resume}>Resume{pending.length ? ` (${pending.length} new)` : ""}</button>
            : <button className="btn small" type="button" onClick={() => setHold(true)}>Pause the feed</button>}
        </div>
        {recent.loading && !recent.data ? <Loading /> : <ErrorBox error={recent.error} />}
        {recent.data && (shown.length === 0 ? <Empty>{rows.length ? "No message matches the filter." : "No message yet. New ones appear here as they arrive."}</Empty> : (
          <table className="feed">
            <thead><tr><th>Time</th><th>Channel</th><th>Came from</th><th>Recipient</th><th>Message score</th><th>Campaign at arrival</th><th>Indicators</th></tr></thead>
            <tbody>{shown.map((m) => (
              <tr key={m.id} className={`${fresh.has(m.id) ? "flash" : ""} ${m.campaign_id ? "click" : ""}`} tabIndex={m.campaign_id ? 0 : undefined}
                onClick={() => m.campaign_id && nav(`/app/campaigns/${m.campaign_id}`)} onKeyDown={(e) => e.key === "Enter" && m.campaign_id && nav(`/app/campaigns/${m.campaign_id}`)}>
                <td className="small nw" data-label="Time" title={`received ${fmtTime(m.received_at)}`}>{ago(m.at, now)}</td>
                <td className="nw" data-label="Channel">{m.channel}</td>
                <td className="small" data-label="Came from">{SOURCE[m.source] || m.source}{m.origin && <div className="muted">{m.origin}</div>}</td>
                <td className="small wrap" data-label="Recipient">{m.recipient}</td>
                <td className="nw" data-label="Message score"><RiskBadge score={m.assessed ? m.score : null} /></td>
                <td className="small nw" data-label="Campaign at arrival">{m.campaign_id ? <>#{m.campaign_id} · {score3(m.campaign_risk)}{(m.campaign_risk ?? 0) >= ALERT_LINE && <span className="badge alert" style={{ marginLeft: 6 }}>alert</span>}</> : <span className="muted">—</span>}</td>
                <td data-label="Indicators">{m.indicators.length ? m.indicators.slice(0, 2).map((i) => <span className="chip mono" key={i}>{i}</span>) : <span className="muted small">—</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        The message score is the detector's score for that message alone. The campaign score is the risk of the person's campaign when the message arrived;
        it can rise as more messages join. Scores are not probabilities. Calls and video are shown as not assessed.
      </p>
    </>
  );
}
