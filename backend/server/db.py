"""The app's own database (accounts, organisations, API keys, alert triage, logs). Message events live in each organisation's own event store
(engine.py), not here. SQLite by default; MCPD_DATABASE_URL can point to PostgreSQL. Times are epoch seconds (UTC)."""
import time
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import get_settings

ROLES = ("viewer", "analyst", "admin", "superadmin")
RANK = {r: i for i, r in enumerate(ROLES)}
CASE_STATUSES = ("new", "investigating", "confirmed", "false_alarm", "closed")


def now() -> float: return time.time()


class Base(DeclarativeBase): pass


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    keep_labels: Mapped[bool] = mapped_column(Boolean, default=True)       # keep recipient names and plain shared indicators on alert cases
    store_content: Mapped[bool] = mapped_column(Boolean, default=False)    # keep message text in the event store
    created_at: Mapped[float] = mapped_column(Float, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True)      # None for the consultant (superadmin)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_login_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    active_org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    name: Mapped[str] = mapped_column(String(200))
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class AlertCase(Base):
    """The analyst's view of an engine alert: triage status, assignee and notes."""
    __tablename__ = "alert_cases"
    __table_args__ = (UniqueConstraint("org_id", "engine_alert_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    engine_alert_id: Mapped[int] = mapped_column(Integer)
    campaign_id: Mapped[int] = mapped_column(Integer)
    recipient_label: Mapped[str] = mapped_column(String(320), default="")    # empty when the organisation keeps no labels
    recipient_ref: Mapped[str] = mapped_column(String(20))                    # first hex digits of the recipient's HMAC
    risk: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    indicators: Mapped[str] = mapped_column(Text, default="[]")              # JSON list: shared identity tokens (plain only if labels are kept)
    channels: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="new")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="web")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class AlertNote(Base):
    __tablename__ = "alert_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("alert_cases.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class ScanLog(Base):
    """One row per scoring request: what kind, which channel, the result. Never the message."""
    __tablename__ = "scan_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))            # scan, correlate, events
    channel: Mapped[str] = mapped_column(String(20), default="")
    n_events: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Connector(Base):
    """A message source the server reads by itself (connectors.py): an IMAP mailbox, a Microsoft 365 mailbox through Microsoft Graph, or the
    demo replay. Its password or client secret is stored encrypted (secretbox.py) and never returned by the API."""
    __tablename__ = "connectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                        # imap, graph, demo
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[str] = mapped_column(Text, default="{}")              # JSON, never a secret
    secret: Mapped[str] = mapped_column(Text, default="")                # encrypted
    state: Mapped[str] = mapped_column(Text, default="{}")               # JSON: where reading got to
    status: Mapped[str] = mapped_column(String(20), default="new")       # new, connecting, live, polling, error, paused, finished
    detail: Mapped[str] = mapped_column(String(500), default="")         # last status line or error; never message content
    last_checked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_message_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_messages: Mapped[int] = mapped_column(Integer, default=0)
    n_alerts: Mapped[int] = mapped_column(Integer, default=0)
    n_skipped: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)


class MessageLog(Base):
    """One row per message recorded, for the live feed: channel, score, source, campaign. Never the text. The recipient's name and the plain
    indicators are kept only when the organisation keeps labels, as on alert cases."""
    __tablename__ = "message_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    at: Mapped[float] = mapped_column(Float)                              # the message's time
    received_at: Mapped[float] = mapped_column(Float, default=now)        # when the service recorded it
    channel: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))                       # mailbox, sms-hook, mail-hook, api, web, demo
    origin: Mapped[str] = mapped_column(String(200), default="")          # the connector's or API key's name
    recipient_label: Mapped[str] = mapped_column(String(320), default="")
    recipient_ref: Mapped[str] = mapped_column(String(20), default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(40), default="")
    assessed: Mapped[bool] = mapped_column(Boolean, default=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    indicators: Mapped[str] = mapped_column(Text, default="[]")


class SeenMessage(Base):
    """Keyed hashes of the emails already recorded, so a message read twice (a restart, a mailbox and a report) is counted once."""
    __tablename__ = "seen_messages"
    __table_args__ = (UniqueConstraint("org_id", "key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=now)


class AlertHook(Base):
    """Where to POST a short notice when an alert opens (hooks_out.py). The signing secret is encrypted."""
    __tablename__ = "alert_hooks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), unique=True)
    url: Mapped[str] = mapped_column(String(1000))
    secret: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[str] = mapped_column(String(300), default="")
    last_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_sent: Mapped[int] = mapped_column(Integer, default=0)
    n_failed: Mapped[int] = mapped_column(Integer, default=0)


class Lead(Base):
    """A 'request a pilot' message from the public website."""
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    organisation: Mapped[str] = mapped_column(String(200), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=now)


_engine = _Session = None


def init_db():
    global _engine, _Session
    url = get_settings().database_url; lite = url.startswith("sqlite")
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if lite else {}, pool_pre_ping=True)
    if lite:
        @event.listens_for(_engine, "connect")
        def _wal(conn, _):             # connector threads write while pages read: write-ahead logging lets readers carry on
            cur = conn.cursor(); cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA busy_timeout=30000"); cur.close()
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session():
    if _Session is None: init_db()
    return _Session()


def get_db():
    db = session()
    try: yield db
    finally: db.close()


def audit(db, action, user=None, org_id=None, detail=""):
    db.add(AuditLog(org_id=org_id if org_id is not None else (user.org_id if user else None), user_id=user.id if user else None, action=action, detail=detail[:2000]))
