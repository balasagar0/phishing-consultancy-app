"""Shared helpers: paths, text cleaning, de-duplication, metrics."""
import re, html, json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import (precision_score, recall_score, f1_score, accuracy_score,
                             roc_auc_score, average_precision_score, confusion_matrix)

ROOT = Path(__file__).resolve().parents[1]
RAW, MODELS, REPORTS = ROOT / "data" / "raw", ROOT / "models", ROOT / "reports"
MODELS.mkdir(exist_ok=True, parents=True); REPORTS.mkdir(exist_ok=True, parents=True)
SEED = 42

_TAG = re.compile(r"<[a-zA-Z/!?][^>]{0,500}>")                                               # a tag starts with a letter, / or !; "a < b" is text
_SCRIPT = re.compile(r"<(script|style|head|title)\b[^>]{0,500}>.*?</\1\s*>", re.I | re.S)          # tag AND its content: code and CSS are not message text
_HREF = re.compile(r"<a\b[^>]{0,500}?\bhref\s*=\s*[\"']?([^\"'\s>]+)[\"']?[^>]{0,500}>", re.I)      # keep a link's target as a URL in the text
_QP = re.compile(r"=([0-9A-Fa-f]{2})")
_WS = re.compile(r"\s+")
_ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_SP_PUNCT = re.compile(r"\s+([.,;:!?)])")
_YEAR = re.compile(r"(?<![A-Za-z])(?:19|20)\d{2}(?![A-Za-z\d])")
_NUM = re.compile(r"(?<![A-Za-z])\d[\d,.\-/:]*\d(?![A-Za-z])|(?<![A-Za-z])\d(?![A-Za-z])")


def _qp_decode(m):
    c = int(m.group(1), 16)
    return chr(c) if 0x20 <= c <= 0x7E else m.group(0)


def clean_text(t, max_chars=2500, mask_numbers=False):
    """Email text cleaner. Drops <script>/<style> blocks with their content, keeps link targets (href) as URLs,
    strips the remaining HTML tags, decodes =3A style escapes (an artifact that only the fraud corpus carries,
    so it would leak the label), normalises spacing. Anything that is not text gives an empty string."""
    if not isinstance(t, str):
        return ""
    t = _SCRIPT.sub(" ", t)
    t = _HREF.sub(lambda m: f" {m.group(1)} ", t)
    t = _TAG.sub(" ", t)
    t = _QP.sub(_qp_decode, t)
    t = _TAG.sub(" ", t)
    t = html.unescape(t)
    t = _ZW.sub("", t)
    t = _SP_PUNCT.sub(r"\1", t)
    if mask_numbers:   # years / phone numbers / amounts identify the corpus era, not the label
        t = _NUM.sub(" numtok ", _YEAR.sub(" yeartok ", t))
    return _WS.sub(" ", t).strip()[:max_chars]


def norm_key(t):
    return hashlib.md5(re.sub(r"[^a-z0-9]+", "", str(t).lower()).encode()).hexdigest()


def dedupe(df, text_col, label_col):
    """Drop exact duplicates (after normalisation) and drop texts that carry conflicting labels."""
    df = df.copy()
    df["_k"] = df[text_col].map(norm_key)
    n0 = len(df)
    nun = df.groupby("_k")[label_col].nunique()
    conflict = set(nun[nun > 1].index)
    df = df[~df["_k"].isin(conflict)].drop_duplicates("_k")
    stats = {"rows_before": int(n0), "rows_after": int(len(df)), "conflicting_texts_dropped": int(len(conflict))}
    return df.drop(columns="_k"), stats


def binary_metrics(y, p, thr=0.5):
    y = np.asarray(y).astype(int); p = np.asarray(p, dtype=float)
    pred = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    out = dict(n=len(y), positives=int(y.sum()), threshold=thr,
               accuracy=accuracy_score(y, pred),
               precision=precision_score(y, pred, zero_division=0),
               recall=recall_score(y, pred, zero_division=0),
               f1=f1_score(y, pred, zero_division=0),
               false_positive_rate=fp / max(fp + tn, 1),
               tn=tn, fp=fp, fn=fn, tp=tp)
    if len(set(y)) == 2:
        out["roc_auc"] = roc_auc_score(y, p)
        out["pr_auc"] = average_precision_score(y, p)
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else int(v) if isinstance(v, (np.integer,)) else v)
            for k, v in out.items()}


def threshold_at_fpr(y, p, fpr=0.01):
    neg = np.asarray(p)[np.asarray(y) == 0]
    return float(np.quantile(neg, 1 - fpr))


def bootstrap_ci(y, p, thr=0.5, B=300, seed=SEED):
    """95% bootstrap CI for precision / recall / F1 (matters for small classes like SMS smishing)."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y).astype(int); pred = (np.asarray(p) >= thr).astype(int)
    res = {"precision": [], "recall": [], "f1": []}
    for _ in range(B):
        i = rng.integers(0, len(y), len(y))
        res["precision"].append(precision_score(y[i], pred[i], zero_division=0))
        res["recall"].append(recall_score(y[i], pred[i], zero_division=0))
        res["f1"].append(f1_score(y[i], pred[i], zero_division=0))
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in res.items()}


def save_json(obj, path):
    def conv(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, (np.ndarray,)): return o.tolist()
        return str(o)
    Path(path).write_text(json.dumps(obj, indent=2, default=conv))
