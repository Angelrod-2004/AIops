"""Shared plumbing for every tool: JSON envelopes, time parsing, API clients."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config


# --------------------------------------------------------------------------- #
# Result envelopes - every tool returns a JSON *string* so that the same value
# can be printed in the UI, fed back to an LLM, or logged.
# --------------------------------------------------------------------------- #
def to_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def ok(**payload: Any) -> str:
    return to_json({"ok": True, **payload})


def err(message: str, **payload: Any) -> str:
    return to_json({"ok": False, "error": str(message), **payload})


def simulated(app: str, action: str, **payload: Any) -> str:
    return to_json(
        {
            "ok": True,
            "simulated": True,
            "app": app,
            "action": action,
            "note": f"{app} is in SIMULATED mode - add credentials to .env to hit the live API.",
            **payload,
        }
    )


# --------------------------------------------------------------------------- #
# Input helpers
# --------------------------------------------------------------------------- #
def split_csv(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(v).strip() for v in value]
    else:
        items = [part.strip() for part in str(value).replace(";", ",").split(",")]
    return [item for item in items if item]


def parse_json_arg(value: Any, field: str = "payload") -> Any:
    """Accept a JSON string (or an already-parsed object) and validate it."""
    if value in (None, "", (), [], {}):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"`{field}` must be valid JSON ({exc.msg} at char {exc.pos})") from exc


def adf(text: str) -> dict[str, Any]:
    """Jira Cloud v3 requires Atlassian Document Format for rich text fields."""
    blocks = [block for block in str(text or "").split("\n\n") if block.strip()]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": block.strip()}]} for block in blocks
        ]
        or [{"type": "paragraph", "content": []}],
    }


def plain_text(node: Any) -> str:
    """Flatten an ADF document (or plain string) back into readable text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(plain_text(item) for item in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") == "hardBreak":
            return "\n"
        return plain_text(node.get("content", []))
    return ""


# --------------------------------------------------------------------------- #
# Time helpers - accept ISO-8601 *and* natural language ("tomorrow 3pm")
# --------------------------------------------------------------------------- #
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY_ALIASES = {
    "mon": "monday", "tue": "tuesday", "tues": "tuesday", "wed": "wednesday",
    "thu": "thursday", "thur": "thursday", "thurs": "thursday",
    "fri": "friday", "sat": "saturday", "sun": "sunday",
}
_TIME_OF_DAY = {
    "midnight": "00:00", "morning": "09:00", "noon": "12:00", "midday": "12:00",
    "afternoon": "15:00", "evening": "18:00", "tonight": "20:00", "night": "20:00",
}
_UNITS = {"minute": "minutes", "hour": "hours", "day": "days", "week": "weeks"}
_CLOCK_RE = re.compile(r"\d{1,2}:\d{2}|\d{1,2}\s*(am|pm)\b")
_TIME_OF_DAY_RE = re.compile(r"\b(" + "|".join(sorted(_TIME_OF_DAY, key=len, reverse=True)) + r")\b")
_WEEKDAY_RE = re.compile(
    r"\b(?:(next|this|coming|upcoming)\s+)?(" + "|".join(list(_WEEKDAYS) + list(_WEEKDAY_ALIASES)) + r")\b"
)
_RELATIVE_RE = re.compile(r"(?:\bin\b|\+)\s*(\d+)\s*(minute|hour|day|week)s?\b")
_DROP_WORDS = re.compile(r"\b(at|on|the|of|by|around)\b")


def parse_dt(value: str, tz: str | None = None) -> datetime:
    """Parse ISO-8601 or friendly phrases: 'tomorrow 3pm', 'next monday', 'in 2 hours'."""
    from dateutil import parser as date_parser
    from dateutil import tz as date_tz

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            zone = date_tz.gettz(tz or config.DEFAULT_TIMEZONE) or timezone.utc
            dt = dt.replace(tzinfo=zone)
        return dt

    raw = str(value or "").strip()
    text = raw.lower()
    zone = date_tz.gettz(tz or config.DEFAULT_TIMEZONE) or timezone.utc
    now = datetime.now(zone)
    if text in ("", "now"):
        return now

    relative = _RELATIVE_RE.search(text)
    if relative:
        amount = int(relative.group(1))
        return now + timedelta(**{_UNITS[relative.group(2)]: amount})

    has_clock = bool(_CLOCK_RE.search(text)) or bool(_TIME_OF_DAY_RE.search(text))
    normalized = text

    weekday = _WEEKDAY_RE.search(normalized)
    if weekday:
        name = _WEEKDAY_ALIASES.get(weekday.group(2), weekday.group(2))
        target = _WEEKDAYS.index(name)
        delta = (target - now.weekday()) % 7
        if weekday.group(1) in ("next", "coming", "upcoming") and delta == 0:
            delta = 7
        base = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
        normalized = normalized[: weekday.start()] + base + normalized[weekday.end():]

    if "tomorrow" in normalized:
        normalized = normalized.replace("tomorrow", (now + timedelta(days=1)).strftime("%Y-%m-%d"))
    if "today" in normalized:
        normalized = normalized.replace("today", now.strftime("%Y-%m-%d"))
    if "yesterday" in normalized:
        normalized = normalized.replace("yesterday", (now - timedelta(days=1)).strftime("%Y-%m-%d"))

    normalized = _TIME_OF_DAY_RE.sub(lambda m: _TIME_OF_DAY[m.group(1)], normalized)

    normalized = _DROP_WORDS.sub(" ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().rstrip(".")

    default = now.replace(minute=0, second=0, microsecond=0)
    if not has_clock:
        default = default.replace(hour=9, minute=0)

    try:
        dt = date_parser.parse(normalized, default=default)
    except (ValueError, OverflowError) as exc:
        raise ValueError(
            f"Could not read the date/time '{value}'. Try 'tomorrow 3pm', 'next monday 09:30', "
            f"'in 2 hours' or '2026-11-02T15:00:00'."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return dt


def rfc3339(value: str, tz: str | None = None) -> str:
    if not value:
        return ""
    return parse_dt(value, tz).isoformat()


def human_time(value: Any) -> str:
    if not value:
        return ""
    try:
        return parse_dt(str(value)).strftime("%a %d %b %Y · %H:%M")
    except Exception:
        return str(value)


# --------------------------------------------------------------------------- #
# Google API client (shared by Gmail + Calendar)
# --------------------------------------------------------------------------- #
_SERVICE_CACHE: dict[tuple[str, str], Any] = {}


def google_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = config.GOOGLE_TOKEN_PATH
    if not token_path.exists():
        raise RuntimeError(
            "Google account not linked. Put your OAuth client at "
            f"{config.GOOGLE_CLIENT_SECRET_PATH} and run `python scripts/google_auth.py`."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), config.GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def google_service(api: str, version: str):
    key = (api, version)
    if key not in _SERVICE_CACHE:
        from googleapiclient.discovery import build

        _SERVICE_CACHE[key] = build(api, version, credentials=google_credentials(), cache_discovery=False)
    return _SERVICE_CACHE[key]


def gmail_service():
    return google_service("gmail", "v1")


def calendar_service():
    return google_service("calendar", "v3")


# --------------------------------------------------------------------------- #
# Jira REST client
# --------------------------------------------------------------------------- #
def jira_request(method: str, path: str, *, raw: bool = False, **kwargs: Any) -> Any:
    import requests

    url = f"{config.JIRA_BASE_URL}/rest/{path.lstrip('/')}"
    headers = {"Accept": "application/json", **kwargs.pop("headers", {})}
    if "json" not in kwargs and "data" not in kwargs and "files" not in kwargs:
        headers.setdefault("Content-Type", "application/json")
    response = requests.request(
        method.upper(),
        url,
        auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
        headers=headers,
        timeout=60,
        **kwargs,
    )
    if response.status_code >= 400:
        detail = response.text[:600]
        try:
            body = response.json()
            detail = "; ".join(body.get("errorMessages", [])) or str(body.get("errors", body))[:600]
        except Exception:
            pass
        raise RuntimeError(f"Jira {response.status_code}: {detail}")
    if raw:
        return response
    return response.json() if response.content else {}


# --------------------------------------------------------------------------- #
# WhatsApp Cloud API client
# --------------------------------------------------------------------------- #
def wa_base() -> str:
    return f"https://graph.facebook.com/{config.WHATSAPP_VERSION}"


def wa_request(method: str, path: str, *, raw: bool = False, **kwargs: Any) -> Any:
    import requests

    headers = {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}", **kwargs.pop("headers", {})}
    if "json" not in kwargs and "files" not in kwargs:
        headers.setdefault("Content-Type", "application/json")
    response = requests.request(method.upper(), f"{wa_base()}/{path.lstrip('/')}", headers=headers, timeout=60, **kwargs)
    if response.status_code >= 400:
        detail = response.text[:600]
        try:
            body = response.json().get("error", {})
            detail = f"{body.get('message', detail)} (code {body.get('code')})"
        except Exception:
            pass
        raise RuntimeError(f"WhatsApp {response.status_code}: {detail}")
    if raw:
        return response
    return response.json() if response.content else {}


def wa_media_payload(media_ref: str, kind: str, caption: str = "", filename: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"messaging_product": "whatsapp", "type": kind}
    key = "id" if media_ref.isdigit() and len(media_ref) > 12 else "link"
    body: dict[str, Any] = {key: media_ref}
    if caption and kind in ("image", "video", "document"):
        body["caption"] = caption
    if filename and kind == "document":
        body["filename"] = filename
    payload[kind] = body
    return payload


def save_bytes(path: str, data: bytes) -> str:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return str(target)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def mime_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def days_from_now(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
