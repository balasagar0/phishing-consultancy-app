"""Cross-channel correlation model.  Input: a bundle of events (channel, detector score, identity tokens, time).
Output: probability that the bundle contains malicious activity, learned from SIMULATED bundles.
Why simulated: no public dataset links one attacker's email, SMS and URL events. Bundles are built from REAL held-out messages scored
by the REAL detectors (email scores come from models that never saw that corpus); what is assumed is the bundle structure (see ASSUMPTIONS)."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np

CH = ["email", "sms", "url"]
T_MAX = 72 * 60  # minutes
DEFAULT_WINDOW_MIN = 60.0   # events further apart than this are not combined or linked. About 95% of simulated attack bundles fit in it (results.md). Replace with the value refit_fusion.py suggests from real bundles.
FEATURE_NAMES = ["n_events", "n_channels", "max_logit", "mean_logit", "min_logit", "email_logit", "sms_logit", "url_logit",
                 "has_email", "has_sms", "has_url", "shares_identity", "n_shared_identities", "frac_events_linked", "log_time_span_min"]
CORR_COLS = [11, 12, 13, 14]   # the columns that carry link / timing evidence
ASSUMPTIONS = {
    "bundle_mix": {"attack_linked": .30, "attack_single": .10, "mixed_unlinked": .10, "benign_linked": .20, "benign_unlinked": .30},
    "label": "1 if any event in the bundle is truly malicious (attack_linked, attack_single, mixed_unlinked), else 0",
    "attack_linked": "2-3 malicious events on different channels, shared identity, gaps ~ Exponential(mean 15 min); each event's identity observed with prob 0.85",
    "benign_linked": "2-3 benign events on different channels, shared identity, gaps Exponential with mean 30 min (50%) or 6 h (50%)",
    "unlinked_bundles": "events with distinct identities, times uniform over 72 h; with prob 0.08 a spurious shared identity is added",
    "scores": "each event gets the real held-out score of a randomly drawn real message of the right class and channel"}


def _logit(p):
    p = min(max(float(p), 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


def bundle_features(ev, strip=False):
    """ev: list of {channel, score, ids, t(minutes)}. strip=True hides all correlation evidence (no shared identity, events 72 h apart)."""
    n = len(ev); lg = [_logit(e["score"]) for e in ev]
    cnt = Counter() if strip else Counter(tok for e in ev for tok in set(e["ids"]))
    shared = [t for t, c in cnt.items() if c >= 2]
    linked = sum(1 for e in ev if any(cnt[t] >= 2 for t in e["ids"])) / n
    ts = [e["t"] for e in ev]; span = 0.0 if n == 1 else (T_MAX if strip else min(T_MAX, max(ts) - min(ts)))   # capped: the model never saw a span above T_MAX
    per = [max([_logit(e["score"]) for e in ev if e["channel"] == c], default=0.0) for c in CH]
    pres = [float(any(e["channel"] == c for e in ev)) for c in CH]
    return np.array([n, len({e["channel"] for e in ev}), max(lg), float(np.mean(lg)), min(lg), *per, *pres,
                     float(len(shared) > 0), len(shared), linked, np.log1p(span)], dtype=float)


def time_windows(ev, window):
    """Splits a bundle into time windows. A window starts at one event and holds every event that follows it within `window` minutes.
    Only events in the same window are combined and linked. A window that sits inside a larger one is dropped.
    window=None (or infinity) gives one window with every event. Returns lists of indices into ev."""
    n = len(ev)
    if n == 0: return []
    if window is None or window == float("inf"): return [list(range(n))]
    order = sorted(range(n), key=lambda i: ev[i]["t"]); sets = []
    for a in order:
        g = frozenset(i for i in order if ev[a]["t"] <= ev[i]["t"] <= ev[a]["t"] + window)
        if g not in sets: sets.append(g)
    sets = [g for g in sets if not any(g < h for h in sets)]
    return [sorted(g, key=lambda i: (ev[i]["t"], i)) for g in sets]


def windowed_risk(model, ev, window=DEFAULT_WINDOW_MIN):
    """Bundle risk under a time window: every window is scored on its own and the bundle takes the highest one.
    A window with one event is that event's detector score; a window with two or more goes to the correlation model.
    risk_without_correlation scores ALL events together with link and timing evidence hidden (no window, no shared identity).
    `model` is Fusion.model (it already carries the single-event rule)."""
    if not ev: raise ValueError("no events")
    wins = window_risks(model, ev, window)
    k = int(np.argmax([r for _, r, _ in wins]))
    p0 = float(model.predict_proba(bundle_features(ev, strip=True)[None, :])[0, 1])
    return {"risk": wins[k][1], "risk_without_correlation": p0, "x": wins[k][2], "window_events": wins[k][0], "n_windows": len(wins)}


def window_risks(model, ev, window=DEFAULT_WINDOW_MIN):
    """Every time window of `ev` with its risk: a list of (event indices, risk, features). The one scorer behind /correlate
    (windowed_risk takes the highest window) and the event store (each window is a campaign)."""
    groups = time_windows(ev, window)
    xs = [bundle_features([ev[i] for i in g]) for g in groups]
    p = model.predict_proba(np.stack(xs))[:, 1]
    return [(g, float(r), x) for g, r, x in zip(groups, p, xs)]


def simulate(pools, n, rng):
    """pools: {channel: {0: benign scores, 1: malicious scores}} -> list of (events, y, type)."""
    draw = lambda ch, mal: float(pools[ch][mal][rng.integers(len(pools[ch][mal]))])
    out = []
    for i in range(n):
        r = rng.random()
        typ = ("attack_linked" if r < .30 else "attack_single" if r < .40 else "mixed_unlinked" if r < .50 else "benign_linked" if r < .70 else "benign_unlinked")
        if typ == "attack_single":
            chs, mal = [CH[rng.integers(3)]], [1]
        elif typ in ("attack_linked", "benign_linked"):
            k = 2 if rng.random() < .6 else 3; chs = list(rng.choice(CH, k, replace=False)); mal = [1 if typ == "attack_linked" else 0] * k
        elif typ == "mixed_unlinked":
            k = 2 if rng.random() < .6 else 3; chs = list(rng.choice(CH, k, replace=False)); mal = [0] * k; mal[rng.integers(k)] = 1
        else:
            k = int(rng.choice([1, 2, 3], p=[.3, .4, .3])); chs = list(rng.choice(CH, k, replace=False)); mal = [0] * k
        k = len(chs); linked = typ in ("attack_linked", "benign_linked")
        if typ == "attack_linked": gaps = rng.exponential(15, k - 1)
        elif typ == "benign_linked": gaps = rng.exponential(30 if rng.random() < .5 else 360, k - 1)
        ts = np.concatenate([[0.0], np.cumsum(gaps)]) if linked else rng.uniform(0, T_MAX, k)
        ev = []
        for j in range(k):
            ids = {f"u{i}_{j}"}
            if linked and (typ == "benign_linked" or rng.random() < .85): ids.add(f"camp{i}")
            ev.append({"channel": chs[j], "score": draw(chs[j], mal[j]), "ids": ids, "t": float(ts[j])})
        if not linked and k >= 2 and rng.random() < .08:
            for e in ev: e["ids"].add(f"generic{i}")
        out.append((ev, int(any(mal)), typ))
    return out


class StackedFusion:
    """Recalibrates the simulation-trained model on REAL bundles: logistic regression on
    [logit(base risk), shares_identity, n_shared_identities, frac_events_linked, log_time_span] (5 parameters, suits small real datasets)."""
    def __init__(self, base, lr):
        self.base, self.lr = base, lr
    def _z(self, X):
        p = np.clip(self.base.predict_proba(X)[:, 1], 1e-4, 1 - 1e-4)
        return np.column_stack([np.log(p / (1 - p)), X[:, CORR_COLS]])
    def predict_proba(self, X):
        return self.lr.predict_proba(self._z(X))


class SingleEventPassThrough:
    """A window with one event has nothing to correlate, so its risk is the channel detector's own score (the sigmoid of max_logit).
    Windows with two or more events go to the wrapped model. Without this, the simulation's 50% attack rate would inflate the risk of a lone event
    (a URL scoring 0.45 alone was rated 0.82)."""
    def __init__(self, model):
        self.model = model
    def predict_proba(self, X):
        X = np.asarray(X, dtype=float); p = np.asarray(self.model.predict_proba(X))[:, 1].copy(); one = X[:, 0] == 1
        p[one] = 1.0 / (1.0 + np.exp(-X[one, 2]))
        return np.column_stack([1.0 - p, p])


class Fusion:
    def __init__(self, path):
        import joblib
        d = joblib.load(path); m, self.meta = d["model"], d["meta"]
        if isinstance(m, StackedFusion):          # refit on real bundles: its base model gets the same single-event rule
            if not isinstance(m.base, SingleEventPassThrough): m.base = SingleEventPassThrough(m.base)
            self.model = m
        else: self.model = m if isinstance(m, SingleEventPassThrough) else SingleEventPassThrough(m)
        self.trained_on = self.meta.get("trained_on", "simulated bundles")
        self.window = float(self.meta.get("window_minutes", DEFAULT_WINDOW_MIN))   # a refit on real bundles can store its own window
    def risk(self, ev, window=None):
        """window: minutes (None = this model's window). Events further apart are not combined or linked."""
        w = self.window if window is None else float(window)
        r = windowed_risk(self.model, ev, w)
        return {"risk": round(r["risk"], 4), "risk_without_correlation": round(r["risk_without_correlation"], 4),
                "features": dict(zip(FEATURE_NAMES, np.round(r["x"], 3).tolist())), "window_minutes": w,
                "n_windows": r["n_windows"], "window_events": r["window_events"]}
