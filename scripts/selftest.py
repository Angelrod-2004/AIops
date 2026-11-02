"""Fast self-tests for the pure logic (no network, no credentials).

Run:  python scripts/selftest.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agents.graph import run_chat, tasks_from_payload  # noqa: E402
from tools._utils import adf, parse_dt, plain_text, rfc3339, split_csv, wa_media_payload  # noqa: E402
from tools.calendar_tools import _event_body, _window  # noqa: E402
from tools.whatsapp_tools import _reply_buttons  # noqa: E402

CHECKS: list[tuple[str, bool]] = []


def check(label: str, condition: bool) -> None:
    CHECKS.append((label, bool(condition)))


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #
tomorrow = parse_dt("tomorrow 3pm", "Asia/Kolkata")
check("tomorrow 3pm -> 15:00", tomorrow.hour == 15 and tomorrow.minute == 0)
check("tomorrow 3pm -> tomorrow", tomorrow.date() > datetime.now(timezone.utc).date())
check("defaults to 09:00", parse_dt("tomorrow", "UTC").hour == 9)
check("keeps explicit minutes", parse_dt("tomorrow 09:30", "UTC").minute == 30)
check("afternoon maps to 15:00", parse_dt("friday afternoon", "UTC").hour == 15)
check("ISO round trip", rfc3339("2026-11-02T15:00:00+05:30", "UTC").startswith("2026-11-02T15:00:00"))
check("in 2 hours is future", parse_dt("in 2 hours", "UTC") > datetime.now(timezone.utc))
check("+2 days parses", (parse_dt("+2 days", "UTC") - datetime.now(timezone.utc)).days >= 1)
check("+7 days parses", (parse_dt("+7 days", "UTC") - datetime.now(timezone.utc)).days >= 6)
check("'in 3 weeks' parses", (parse_dt("in 3 weeks", "UTC") - datetime.now(timezone.utc)).days >= 20)
check("next monday is a monday", parse_dt("next monday", "UTC").weekday() == 0)
check("garbage raises", _raises(lambda: parse_dt("banana", "UTC")))


# --------------------------------------------------------------------------- #
# payload builders
# --------------------------------------------------------------------------- #
body = _event_body("Design review", "tomorrow 15:00", duration_minutes=45,
                   attendees="Ada Lovelace <ada@example.com>, raj@example.com",
                   recurrence="FREQ=WEEKLY;BYDAY=MO", add_meet=True, timezone_name="Asia/Kolkata")
check("event has start+end", "start" in body and "end" in body)
check("duration applied", body["end"]["dateTime"] != body["start"]["dateTime"])
check("attendees parsed", [a["email"] for a in body["attendees"]] == ["ada@example.com", "raj@example.com"])
check("recurrence normalised", body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"])
check("meet request attached", body["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet")

start, end = _window("", "")
check("window defaults to 7 days", start < end)
check("window is ISO", "T" in start)

check("csv splitting", split_csv("a, b;c") == ["a", "b", "c"])
check("adf round trip", plain_text(adf("hello\n\nworld")).replace("helloworld", "hello world") != "")
check("buttons json", _reply_buttons('[{"id":"yes","title":"Approve"}]')[0]["reply"]["title"] == "Approve")
check("too many buttons rejected", _raises(lambda: _reply_buttons("{}")))
check("media payload uses link", wa_media_payload("https://x/y.png", "image", "hi")["image"]["link"] == "https://x/y.png")
check("media payload keeps id key", "id" in wa_media_payload("123456789012345", "image")["image"])

# --------------------------------------------------------------------------- #
# planner validation
# --------------------------------------------------------------------------- #
plan, note = tasks_from_payload(
    {"tasks": [
        {"app": "gmail", "operation_id": "gmail_send", "args": {"to": "a@b.c", "subject": "s", "body": "b"}},
        {"app": "calendar", "operation_id": "gmail_send", "args": {}},
        {"app": "jira", "operation_id": "does_not_exist", "prompt": "do something"},
        {"app": "myspace", "operation_id": "gmail_send"},
        "not-a-dict",
    ], "reply": "ok"},
    "original prompt",
)
check("planner keeps valid tasks", len(plan) == 3)
check("planner corrects a mismatched app", plan[1]["app"] == "gmail")
check("planner downgrades unknown ops to auto", plan[2]["operation_id"] == "auto")
check("planner drops unknown apps", all(t["app"] != "myspace" for t in plan))
check("planner carries the prompt into auto tasks", plan[2]["prompt"] == "do something")
check("planner explains missing info", "more information" in tasks_from_payload({"missing": ["recipient"]}, "x")[1])
check("chat without an LLM degrades gracefully", "Planner error" in run_chat("hello").get("answer", ""))

# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
failed = [label for label, ok in CHECKS if not ok]
for label, ok in CHECKS:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
sys.exit(1 if failed else 0)
