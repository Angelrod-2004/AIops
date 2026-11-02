"""Central configuration + live connection status for every integration.

Everything is read from environment variables (or `.env`). Nothing here talks
to the network - it only answers "are we configured, and should we simulate?".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

APPS: tuple[str, ...] = ("gmail", "calendar", "jira", "whatsapp")

APP_META: dict[str, dict[str, str]] = {
    "gmail": {
        "label": "Gmail",
        "icon": "✉",
        "accent": "#ff5f7e",
        "tagline": "Compose, triage, label, forward, archive",
    },
    "calendar": {
        "label": "Google Calendar",
        "icon": "◷",
        "accent": "#5cc8ff",
        "tagline": "Schedule, reschedule, find free time, invite",
    },
    "jira": {
        "label": "Jira",
        "icon": "◆",
        "accent": "#7c7cff",
        "tagline": "File, transition, comment, sprint",
    },
    "whatsapp": {
        "label": "WhatsApp",
        "icon": "◉",
        "accent": "#3ddc84",
        "tagline": "Text, media, templates, interactive",
    },
}


def _env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip()
    return default


def _path(*names: str, default: str) -> Path:
    raw = _env(*names, default=default)
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (ROOT / candidate)


# --------------------------------------------------------------------------- #
# Google (Gmail + Calendar share one OAuth token)
# --------------------------------------------------------------------------- #
GOOGLE_TOKEN_PATH: Path = _path("GOOGLE_TOKEN_PATH", "GMAIL_TOKEN_PATH", default="credentials/google_token.json")
GOOGLE_CLIENT_SECRET_PATH: Path = _path(
    "GOOGLE_CLIENT_SECRET_PATH", "GMAIL_CREDENTIALS_PATH", default="credentials/google_client_secret.json"
)
GOOGLE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar",
]
DEFAULT_TIMEZONE: str = _env("CALENDAR_TIMEZONE", "TZ", default="UTC")

# --------------------------------------------------------------------------- #
# Jira
# --------------------------------------------------------------------------- #
JIRA_BASE_URL: str = _env("JIRA_BASE_URL", "JIRA_URL").rstrip("/")
JIRA_EMAIL: str = _env("JIRA_EMAIL", "JIRA_USERNAME")
JIRA_API_TOKEN: str = _env("JIRA_API_TOKEN", "JIRA_TOKEN")
JIRA_DEFAULT_PROJECT: str = _env("JIRA_DEFAULT_PROJECT", "JIRA_PROJECT_KEY")
JIRA_ISSUE_TYPE: str = _env("JIRA_ISSUE_TYPE", default="Task")

# --------------------------------------------------------------------------- #
# WhatsApp Cloud API
# --------------------------------------------------------------------------- #
WHATSAPP_TOKEN: str = _env("WHATSAPP_TOKEN", "WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID: str = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ID: str = _env("WHATSAPP_BUSINESS_ID", "WHATSAPP_WABA_ID")
WHATSAPP_VERSION: str = _env("WHATSAPP_API_VERSION", default="v21.0")
WHATSAPP_DEFAULT_TO: str = _env("WHATSAPP_DEFAULT_TO")

# --------------------------------------------------------------------------- #
# LLM (used by the planner + chat agent; structured runs work without it)
# --------------------------------------------------------------------------- #
LLM_PROVIDER: str = _env("LLM_PROVIDER", default="openai").lower()
LLM_MODEL: str = _env("LLM_MODEL", default="")
LLM_TEMPERATURE: float = float(_env("LLM_TEMPERATURE", default="0.2"))
LLM_BASE_URL: str = _env("LLM_BASE_URL", "OPENAI_BASE_URL", default="")
OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "LLM_API_KEY")
ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
GOOGLE_API_KEY: str = _env("GOOGLE_API_KEY", "GEMINI_API_KEY")

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "google": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.1",
}

# "auto"   -> simulate only the apps that have no credentials
# "always" -> never touch a real API
# "never"  -> always call the real API (and surface auth errors)
SIMULATE_MODE: str = _env("SIMULATE_MODE", default="auto").lower()
MAX_AGENT_STEPS: int = int(_env("MAX_AGENT_STEPS", default="8"))


def configured(app: str) -> bool:
    """True when real credentials exist for this app."""
    if app == "gmail" or app == "calendar":
        return GOOGLE_TOKEN_PATH.exists()
    if app == "jira":
        return bool(JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN)
    if app == "whatsapp":
        return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID)
    return False


def simulating(app: str) -> bool:
    if SIMULATE_MODE == "always":
        return True
    if SIMULATE_MODE == "never":
        return False
    return not configured(app)


def missing_hints(app: str) -> list[str]:
    """Env vars a user still has to provide to go live."""
    if app in ("gmail", "calendar"):
        hints = []
        if not GOOGLE_CLIENT_SECRET_PATH.exists():
            hints.append("credentials/google_client_secret.json  (GOOGLE_CLIENT_SECRET_PATH)")
        if not GOOGLE_TOKEN_PATH.exists():
            hints.append("run `python scripts/google_auth.py`  ->  credentials/google_token.json")
        return hints
    if app == "jira":
        return [k for k, v in (("JIRA_BASE_URL", JIRA_BASE_URL), ("JIRA_EMAIL", JIRA_EMAIL), ("JIRA_API_TOKEN", JIRA_API_TOKEN)) if not v]
    if app == "whatsapp":
        return [k for k, v in (("WHATSAPP_TOKEN", WHATSAPP_TOKEN), ("WHATSAPP_PHONE_NUMBER_ID", WHATSAPP_PHONE_NUMBER_ID)) if not v]
    return []


def mode_for(app: str) -> str:
    return "SIMULATED" if simulating(app) else "LIVE"


def llm_configured() -> bool:
    if LLM_PROVIDER == "ollama":
        return True
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if LLM_PROVIDER == "google":
        return bool(GOOGLE_API_KEY)
    if LLM_PROVIDER == "groq":
        return bool(_env("GROQ_API_KEY"))
    return bool(OPENAI_API_KEY)


def model_name() -> str:
    return LLM_MODEL or DEFAULT_MODELS.get(LLM_PROVIDER, "gpt-4o-mini")


@dataclass(frozen=True)
class AppStatus:
    app: str
    label: str
    icon: str
    accent: str
    mode: str
    configured: bool
    hints: list[str]


def status_snapshot() -> list[AppStatus]:
    out: list[AppStatus] = []
    for app in APPS:
        meta = APP_META[app]
        out.append(
            AppStatus(
                app=app,
                label=meta["label"],
                icon=meta["icon"],
                accent=meta["accent"],
                mode=mode_for(app),
                configured=configured(app),
                hints=missing_hints(app),
            )
        )
    return out
