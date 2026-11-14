import { useCallback, useEffect, useState } from "react";

export const ALERT_LINE = 0.5;

export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    return fn().then((data) => setState({ data, error: null, loading: false }), (error) => setState({ data: null, error, loading: false }));
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { ...state, reload: run };
}

export const fmtTime = (s) => (s ? new Date(s * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "never");
export const fmtMinutes = (m) => (m > 1e6 ? new Date(m * 60000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : `minute ${Math.round(m)}`);
export const score3 = (x) => (x === null || x === undefined ? "not assessed" : Number(x).toFixed(3));

export function RiskBadge({ score }) {
  if (score === null || score === undefined) return <span className="badge na" title="No detector for this channel: not assessed, never safe">Not assessed</span>;
  return score >= ALERT_LINE ? <span className="badge alert">Alert · {score3(score)}</span> : <span className="badge low">Below line · {score3(score)}</span>;
}

const STATUS = { new: ["New", "alert"], investigating: ["Investigating", "brand"], confirmed: ["Confirmed phishing", "alert"], false_alarm: ["False alarm", "neutral"], closed: ["Closed", "neutral"] };
export const statusLabel = (s) => (STATUS[s] || [s])[0];
export function StatusBadge({ status }) {
  const [label, kind] = STATUS[status] || [status, "neutral"];
  return <span className={`badge ${kind}`}>{label}</span>;
}

export function ScoreBar({ score, label = "Score" }) {
  if (score === null || score === undefined) return <div className="note warn">Not assessed: there is no detector for this channel. This is not a "safe" verdict.</div>;
  const alert = score >= ALERT_LINE;
  return (
    <div>
      <div className="score-head"><span className="muted small">{label} (0 to 1; alert line {ALERT_LINE})</span><span className="num">{score3(score)}</span></div>
      <div className="scorebar" role="img" aria-label={`${label} ${score3(score)}, alert line ${ALERT_LINE}`}>
        <div className={`fill ${alert ? "alert" : ""}`} style={{ width: `${Math.max(1, score * 100)}%` }} />
        <div className="line" style={{ left: `${ALERT_LINE * 100}%` }} />
      </div>
    </div>
  );
}

/** The words or character groups that moved a score, whatever the channel calls them. */
export function Explanation({ result }) {
  const keys = Object.keys(result || {}).filter((k) => k.startsWith("top_") && Array.isArray(result[k]) && result[k].length);
  if (!keys.length) return null;
  return (
    <div className="grid two">
      {keys.map((k) => (
        <div key={k}>
          <div className="small muted" style={{ fontWeight: 700 }}>{k.replace(/^top_(terms|ngrams)_/, "").replace(/_/g, " ").replace(/^toward/, "Pushed toward")}</div>
          <div>{result[k].map(([t, w]) => <span className="chip mono" key={t} title={`weight ${Number(w).toFixed(3)}`}>{t}</span>)}</div>
        </div>
      ))}
    </div>
  );
}

export const Loading = () => <p className="muted">Loading…</p>;
export const ErrorBox = ({ error }) => (error ? <div className="error" role="alert">{error.message || String(error)}</div> : null);
export const Empty = ({ children }) => <p className="muted">{children}</p>;

export function Tiles({ items }) {
  return <div className="tiles">{items.map(([k, v]) => <div className="tile" key={k}><div className="v">{v}</div><div className="k">{k}</div></div>)}</div>;
}

export function Bars({ data, label }) {
  const max = Math.max(1, ...data.map((d) => d.n));
  return (
    <div>
      <div className="bars" role="img" aria-label={label}>
        {data.map((d, i) => (
          <div className="b" key={d.day} title={`${d.day}: ${d.n}`}>
            <span className="n">{d.n > 0 ? d.n : " "}</span>
            <div className="track"><div className="col" style={{ height: `${(d.n / max) * 100}%` }} /></div>
            <span className="d">{i % 7 === 0 || i === data.length - 1 ? d.day.slice(5) : " "}</span>
          </div>
        ))}
      </div>
      <table className="sr"><caption>{label}</caption><tbody>{data.map((d) => <tr key={d.day}><td>{d.day}</td><td>{d.n}</td></tr>)}</tbody></table>
    </div>
  );
}

export function HBars({ items }) {
  const max = Math.max(1, ...items.map(([, v]) => v));
  if (!items.length) return <Empty>Nothing yet.</Empty>;
  return items.map(([k, v]) => (
    <div className="hbar" key={k}><span>{k}</span><span className="track"><span style={{ width: `${(v / max) * 100}%` }} /></span><span className="mono">{v}</span></div>
  ));
}

export function CopyButton({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  return (
    <button className="btn small" type="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* clipboard blocked */ } }}>
      {done ? "Copied" : label}
    </button>
  );
}
