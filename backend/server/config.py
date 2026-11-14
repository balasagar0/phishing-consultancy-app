"""Settings, read from environment variables (a .env file is read by the start scripts, not here). Every value has a safe default for a
single-machine install. See ../.env.example for the full list."""
import os, secrets
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]          # the app folder


def _load_env_file(p=APP_DIR / ".env"):
    """KEY=VALUE lines from the app folder's .env file. A variable already set in the environment wins."""
    if not p.exists(): return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


if not os.environ.get("MCPD_IGNORE_ENV_FILE"): _load_env_file()


def _bool(name, default):
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    app_name: str = field(default_factory=lambda: os.environ.get("MCPD_APP_NAME", "Multi-Channel Phishing Detection"))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("MCPD_DATA_DIR", str(APP_DIR / "data"))))
    database_url: str = field(default_factory=lambda: os.environ.get("MCPD_DATABASE_URL", ""))
    secure_cookies: bool = field(default_factory=lambda: _bool("MCPD_SECURE_COOKIES", False))     # set to 1 behind HTTPS
    session_hours: float = field(default_factory=lambda: float(os.environ.get("MCPD_SESSION_HOURS", "12")))
    purge_interval_hours: float = field(default_factory=lambda: float(os.environ.get("MCPD_PURGE_INTERVAL_HOURS", "24")))
    public_url: str = field(default_factory=lambda: os.environ.get("MCPD_PUBLIC_URL", "").rstrip("/"))    # for links in alert webhooks
    run_connectors: bool = field(default_factory=lambda: _bool("MCPD_RUN_CONNECTORS", True))              # start mailbox connectors with the server
    max_text_chars: int = 100_000
    max_events: int = 20
    login_attempts_before_lock: int = 5
    lock_minutes: int = 15

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url: self.database_url = f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def master_key(self) -> bytes:
        """The secret from which every organisation's HMAC key is derived. MCPD_MASTER_KEY, or a random 256-bit key created once in the
        data folder (keep that file out of backups that leave the server, and never in git)."""
        env = os.environ.get("MCPD_MASTER_KEY")
        if env: return env.encode()
        p = self.data_dir / "master.key"
        if not p.exists():
            p.write_text(secrets.token_hex(32))
            try: os.chmod(p, 0o600)
            except OSError: pass
        return p.read_text().strip().encode()


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None: _settings = Settings()
    return _settings


def reset_settings():
    """Tests change the environment and call this."""
    global _settings
    _settings = None
