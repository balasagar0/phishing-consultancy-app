"""One email (raw MIME) to engine events. Used by the server's mailbox connectors, the email webhook and connectors/imap_connector.py.
Standard library only, so the stand-alone connector can use it too. Nothing here prints or logs message content.

Two modes:
- 'reports': staff forward suspicious mail to a reporting mailbox. An email forwarded as an attachment (message/rfc822) is the suspicious one and
  the person who forwarded it is the recipient. Otherwise the message itself is checked and its first To address is the recipient.
- 'inbox': a mailbox is watched; every new message is checked, and the mailbox's owner is the recipient.
The email (subject and text) is one event with its sender as identity; up to five distinct links in it become URL events. All events of one
email share its time: when it arrived, or for a forwarded report the original's Date when that is believable."""
import email, hashlib, re, time
from email import policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

URL = re.compile(r"""https?://[^\s<>"')\]]+""", re.I)
MAX_RAW = 10 * 1024 * 1024          # larger messages are skipped (counted, not read)
MAX_LINKS = 5


def _text(msg) -> str:
    """The message's plain text, or its HTML if it has no plain text (the engine cleans HTML)."""
    plain, html = [], []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_maintype() == "multipart" or part.get_content_type() == "message/rfc822" or part.get_filename(): continue
        try: body = part.get_content()
        except (LookupError, ValueError, AssertionError): body = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        if not isinstance(body, str): continue
        (plain if part.get_content_type() == "text/plain" else html if part.get_content_type() == "text/html" else []).append(body)
    return "\n".join(plain or html).strip()


def _date(msg):
    try:
        d = parsedate_to_datetime(str(msg.get("Date", "")))
        return d.timestamp() if d.tzinfo else None
    except (TypeError, ValueError, IndexError):
        return None


def links(text: str, limit: int = MAX_LINKS) -> list[str]:
    seen = []
    for u in URL.findall(text or ""):
        u = u.rstrip(".,;:!?")
        if u not in seen: seen.append(u)
        if len(seen) == limit: break
    return seen


def parse(raw: bytes, mode: str = "reports", mailbox: str = "", received_at: float | None = None):
    """Returns {"recipient", "events", "time", "message_id"} for one message, or None when it holds nothing to check."""
    outer = email.message_from_bytes(raw, policy=policy.default); inner = None; now = time.time()
    if mode == "reports":
        for part in outer.walk():
            if part.get_content_type() == "message/rfc822":
                payload = part.get_payload()
                inner = payload[0] if isinstance(payload, list) and payload else payload if isinstance(payload, email.message.Message) else None
                break
    if inner is not None:
        suspicious, recipient = inner, parseaddr(str(outer.get("From", "")))[1]
    else:
        suspicious = outer
        tos = [a for _, a in getaddresses([str(x) for x in outer.get_all("To", [])]) if a]
        recipient = mailbox if (mode == "inbox" and mailbox) else (tos[0] if tos else parseaddr(str(outer.get("From", "")))[1])
    text = _text(suspicious); subject = str(suspicious.get("Subject", "") or "")[:2000]
    if not recipient or not (text or subject): return None
    t = received_at or now
    if inner is not None:                                    # a report: the original's own Date, if it is believable
        d = _date(inner)
        if d is not None and now - 30 * 86400 < d <= now + 300: t = d
    sender = parseaddr(str(suspicious.get("From", "")))[1][:320]
    tm = str(t / 60.0)
    events = [{"channel": "email", "text": (text or subject)[:100000], "subject": subject, "identity": sender, "time": tm}]
    events += [{"channel": "url", "text": u[:2000], "time": tm} for u in links(text)]
    mid = str(suspicious.get("Message-ID", "") or "").strip() or hashlib.sha256(raw).hexdigest()
    return {"recipient": recipient.strip().lower()[:320], "events": events, "time": t, "message_id": mid[:500]}


def events_from_message(raw: bytes):
    """The stand-alone connector's older interface: (recipient, events without times) in 'reports' mode, or (None, [])."""
    p = parse(raw)
    if p is None: return None, []
    return p["recipient"], [{k: v for k, v in e.items() if k != "time"} for e in p["events"]]
