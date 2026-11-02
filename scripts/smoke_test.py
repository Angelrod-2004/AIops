"""End-to-end smoke test: runs the LangGraph fan-out with simulated credentials.

Run:  python scripts/smoke_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402

# Never touch a real API from the test suite: no mail is sent, no event created.
config.SIMULATE_MODE = "always"

from agents.graph import run_plan  # noqa: E402


TASKS = [
    {"id": "t1", "app": "gmail", "operation_id": "gmail_send", "label": "Send email",
     "args": {"to": "ada@example.com", "subject": "Q4 deck", "body": "Numbers look good."}},
    {"id": "t2", "app": "calendar", "operation_id": "cal_create_event", "label": "Create event",
     "args": {"summary": "Design review", "start": "tomorrow 15:00", "duration_minutes": 45,
              "attendees": "ada@example.com", "add_meet": True}},
    {"id": "t3", "app": "jira", "operation_id": "jira_create_issue", "label": "Create issue",
     "args": {"summary": "Checkout latency spike", "project_key": config.JIRA_DEFAULT_PROJECT or "OPS",
              "issue_type": "Bug"}},
    {"id": "t4", "app": "whatsapp", "operation_id": "wa_send_text", "label": "Send text",
     "args": {"to": "919876543210", "body": "Deploy finished"}},
    {"id": "t5", "app": "jira", "operation_id": "jira_create_issue", "label": "Missing field",
     "args": {}},
]


def main() -> int:
    state = run_plan(TASKS)
    results = state.get("results") or []

    print("=" * 78)
    print(state.get("answer", "<no answer>"))
    print("=" * 78)

    failures = 0
    for result in results:
        print(f"[{result['status']:7}] {result['app']:9} {result['label']:16} {result['ms']:>4} ms "
              f"{(result.get('summary') or result.get('error') or '')[:70]}")
        if result["status"] != "success" and result["id"] != "t5":
            failures += 1

    simulated = sum(1 for r in results if (r.get("output") or {}).get("simulated"))
    print(f"\n{len(results)} results · {simulated} simulated · {failures} unexpected failures")

    missing_case = next((r for r in results if r["id"] == "t5"), None)
    if not missing_case or missing_case["status"] != "error" or "Missing required" not in missing_case.get("error", ""):
        print("!! missing-field validation did not fire")
        failures += 1

    if len(results) != len(TASKS):
        print(f"!! expected {len(TASKS)} results, got {len(results)}")
        failures += 1

    print("\nfirst result payload:")
    print(json.dumps(results[0].get("output"), indent=2)[:400] if results else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
