"""Inference wrapper for the trained per-channel detectors (email, sms, url).
score = probability the item is NOT benign (spam / phishing / fraud / smishing / malicious URL).
Voice and video are not trained here (no accessible training data); they raise NotImplementedError."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import joblib
from sklearn.feature_extraction.text import HashingVectorizer
from common import clean_text, MODELS
from scipy import sparse
from url_features import canon, host_of, rep_matrix, reg_domain, rank_of, BUCKETS, _EXT
import re


def _top(names, contrib, k):
    order = np.argsort(contrib)
    pos = [(str(names[i]), round(float(contrib[i]), 4)) for i in order[::-1][:k] if contrib[i] > 0]
    neg = [(str(names[i]), round(float(contrib[i]), 4)) for i in order[:k] if contrib[i] < 0]
    return pos, neg


_LINK = re.compile(r"(?:[a-z][a-z0-9+.\-]*://|www\.)\S+|\b[\w\-]+(?:\.[\w\-]+)+/\S*", re.I)     # links are cut out before phone numbers are looked for (tracking numbers sit inside them)
_PHONE = re.compile(r"(?<![\w+])(\+?)\(?(\d[\d\s\-()]{7,}\d)(?!\w)")
_DATE = re.compile(r"(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])|(?:0?[1-9]|[12]\d|3[01])[-/\s](?:0?[1-9]|1[0-2])[-/\s](?:19|20)\d{2}")
_CALL_CUE = re.compile(r"\b(call|phone|ph|tel|telephone|mobile|mob|whatsapp|contact|dial|helpline|sms|text|cell)\b", re.I)
_ID_CUE = re.compile(r"\b(ref|reference|id|order|tracking|track|awb|waybill|consignment|shipment|parcel|invoice|txn|transaction|utr|a/c|acct|account|policy|ticket|booking|pnr|case)\b", re.I)


def phone_token(raw, plus=False):
    """'tel:<last 10 digits>' when `raw` has the shape of a phone number, else None.
    Accepted: a leading + with 10-15 digits, 10 digits, 11 digits starting with 0, 12 digits starting with 91 and a mobile digit.
    Other digit strings (tracking, order and account numbers) and dates are not phone numbers."""
    raw = str(raw).strip()
    if _DATE.match(raw): return None
    d = re.sub(r"\D", "", raw); n = len(d)
    ok = (plus and 10 <= n <= 15) or n == 10 or (n == 11 and d[0] == "0") or (n == 12 and d[:2] == "91" and d[2] in "6789")
    return "tel:" + d[-10:] if ok else None


def _is_reference(text, start):
    """True when the words just before a number say it is a reference (order, tracking, account...) and nothing says call/phone."""
    before = text[max(0, start - 28):start]
    return bool(_ID_CUE.search(before)) and not _CALL_CUE.search(before)


def extract_ids(channel, text, identity=""):
    """Identity tokens used to link events: registered domains (URL events, URLs/domains in text, e-mail addresses), phone numbers, explicit sender id."""
    ids = set()
    def add_domain(tok):
        tok = tok.strip().strip(".,;:!?()[]<>\"'")
        r = _EXT(host_of(canon(tok)))
        if r.suffix and r.domain: ids.add("dom:" + (getattr(r, "top_domain_under_public_suffix", None) or r.registered_domain))
    if channel == "url": add_domain(text)
    for tok in str(text).split():
        if "." in tok: add_domain(tok.split("@")[-1] if "@" in tok else tok)
    plain = _LINK.sub(" ", str(text))
    for m in _PHONE.finditer(plain):
        tok = phone_token(m.group(2), bool(m.group(1)))
        if tok and not _is_reference(plain, m.start()): ids.add(tok)
    ident = str(identity or "").strip().lower()
    if ident:
        tok = phone_token(ident.lstrip("+("), ident.lstrip("(").startswith("+")) if not re.search(r"[a-z]", ident) and re.search(r"\d", ident) else None
        if tok: ids.add(tok)
        elif "." in ident: add_domain(ident.split("@")[-1])
        else: ids.add("id:" + ident)
    return sorted(ids)


SCORED = ("email", "sms", "url")
NOT_ASSESSED = ("call", "voice", "video")      # accepted as events, never scored: no detector is built for them
MODEL_FILES = {"email": "email_model.joblib", "sms": "sms_model.joblib", "url": "url_string_model.joblib"}


class ModelUnavailable(RuntimeError):
    """The channel has a detector, but its model file could not be loaded when the service started."""


class Detectors:
    def __init__(self, models_dir=MODELS, threshold=0.5):
        """Loads each channel's model on its own. A missing or broken file makes only that channel unavailable (degraded mode, D-14)."""
        d = Path(models_dir); self.threshold = threshold; self.unavailable = {}
        for ch, f in MODEL_FILES.items():
            try: setattr(self, ch, joblib.load(d / f))
            except Exception as e:
                setattr(self, ch, None); self.unavailable[ch] = f"{f} could not be loaded ({type(e).__name__})"
        if self.url is not None:
            self._hv = HashingVectorizer(**self.url["hasher_params"], dtype=np.float32)
            self._gram_hv = HashingVectorizer(analyzer=lambda s: [s], n_features=self.url["hasher_params"]["n_features"], alternate_sign=False, norm=None)
        if self.sms is not None:
            self._sms_names = np.array([n.split("__", 1)[1] for n in self.sms["pipe"][0].get_feature_names_out()])
            self._sms_is_word = np.array([n.startswith("tfidfvectorizer-1__") for n in self.sms["pipe"][0].get_feature_names_out()])

    def available(self, channel):
        return channel in SCORED and channel not in self.unavailable

    # ---- channels ----
    def score_email(self, text, subject="", k=6):
        t = clean_text(f"{subject} . {text}", mask_numbers=self.email["meta"].get("mask_numbers", False))
        v, clf = self.email["vectorizer"], self.email["clf"]
        X = v.transform([t]); p = float(clf.predict_proba(X)[0, 1])
        contrib = np.asarray(X.multiply(clf.coef_[0]).todense()).ravel()
        pos, neg = _top(v.get_feature_names_out(), contrib, k)
        return self._pack("email", p, {"top_terms_toward_malicious": pos, "top_terms_toward_legit": neg})

    def score_sms(self, text, k=6):
        pipe, labels = self.sms["pipe"], self.sms["labels"]
        t = " ".join(str(text).split()); P = pipe.predict_proba([t])[0]
        X = pipe[0].transform([t]); W = pipe[-1].coef_
        toward = 1 + int(np.argmax(P[1:]))               # spam or smishing, whichever is likelier
        contrib = np.asarray(X.multiply(W[toward] - W[0]).todense()).ravel() * self._sms_is_word
        pos, neg = _top(self._sms_names, contrib, k)
        out = self._pack("sms", float(1 - P[0]), {"class_probabilities": {l: round(float(p), 4) for l, p in zip(labels, P)},
                                                  "smishing_probability": round(float(P[2]), 4),
                                                  "top_terms_toward_" + labels[toward]: pos, "top_terms_toward_ham": neg})
        return out

    def score_url(self, url, k=6):
        c = canon(url); m = self.url; h = host_of(c)
        M = m["tfidf"].transform(self._hv.transform([c])).tocsr()
        flags = rep_matrix([h], m["rank_map"]) if m.get("use_rep") else None
        X = sparse.hstack([M, flags]).tocsr() if flags is not None else M
        p = float(m["clf"].predict_proba(X)[0, 1])
        grams = sorted(set(self._hv.build_analyzer()(c)))
        idx = self._gram_hv.transform(grams).indices if grams else np.array([], dtype=int)
        val = dict(zip(M.indices, M.data)); coef = m["clf"].coef_[0]
        contrib = np.array([val.get(i, 0.0) * coef[i] for i in idx])
        pos, neg = _top(np.array(grams), contrib, k) if len(grams) else ([], [])
        rank = rank_of(h, m["rank_map"]); rd = reg_domain(h)
        pop = {"registered_domain": rd, "popularity_rank": rank if rank < 10 ** 9 else None}
        return self._pack("url", p, {"canonical_url": c, "domain_reputation": pop, "top_ngrams_toward_malicious": pos, "top_ngrams_toward_legit": neg})

    def score(self, channel, text, subject=""):
        if channel in self.unavailable: raise ModelUnavailable(f"the {channel} model is not loaded: {self.unavailable[channel]}")
        if channel == "email": return self.score_email(text, subject)
        if channel == "sms": return self.score_sms(text)
        if channel == "url": return self.score_url(text)
        raise NotImplementedError(f"channel '{channel}' has no trained model here (voice/video need audio/video training data)")

    def _pack(self, channel, p, extra):
        return {"channel": channel, "score": round(p, 4), "label": "malicious" if p >= self.threshold else "benign",
                "threshold": self.threshold, **extra}


if __name__ == "__main__":
    import json
    ch, txt = sys.argv[1], " ".join(sys.argv[2:])
    print(json.dumps(Detectors().score(ch, txt), indent=2))
