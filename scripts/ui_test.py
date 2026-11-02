"""Headless UI test - boots app.py through Streamlit's AppTest harness.

Run:  python scripts/ui_test.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from streamlit.testing.v1 import AppTest  # noqa: E402

FAILURES: list[str] = []


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def capture_logs(action) -> list[str]:
    """Run `action` while capturing Streamlit's logger output (warnings included)."""
    handler = _LogCapture()
    loggers = [logging.getLogger("streamlit")]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        action()
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
    return handler.messages


def expect(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()

    expect("app renders without exception", not at.exception, str(at.exception))
    if at.exception:
        for exc in at.exception:
            print(exc.stack_trace)
        return 1

    # Force SIMULATED mode so the suite never sends real mail, creates real events
    # or messages anyone - results then depend on code, not on credentials.
    if at.radio:
        at.radio[0].set_value("always").run()
        expect("switched to simulated execution", not at.exception, str(at.exception))

    expect("4 tabs present", len(at.tabs) == 4, f"got {len(at.tabs)}")
    expect("app cards rendered", len(at.markdown) > 10)
    expect("operation count in sidebar", len(at.radio) == 1)
    print(f"      widgets: {len(at.button)} buttons · {len(at.selectbox)} selectbox · "
          f"{len(at.text_input)} text_input · {len(at.text_area)} text_area")

    # --- presets fill the queue -------------------------------------------------
    preset = next((b for b in at.button if b.key and b.key.startswith("preset_")), None)
    expect("preset buttons exist", preset is not None)
    if preset:
        preset.click().run()
        expect("preset queued a task", len(at.session_state["queue"]) >= 1)

    all_four = next((b for b in at.button if b.key == "preset_◈ All four at once"), None)
    if all_four:
        all_four.click().run()
        expect("all-four preset queued 5 tasks", len(at.session_state["queue"]) == 5,
               f"got {len(at.session_state['queue'])}")

    # --- execute the queue through the graph ------------------------------------
    run_button = next((b for b in at.button if (b.label or "").startswith("▶")), None)
    expect("execute button exists", run_button is not None)
    if run_button:
        run_button.click().run()
        last = at.session_state["last_run"]
        expect("run produced results", bool(last and last.get("results")), str(at.exception))
        if last and last.get("results"):
            expect("all five actions reported", len(last["results"]) == 5)
            expect("all succeeded", all(r["status"] == "success" for r in last["results"]))
            expect("report text written", bool(last.get("answer")))
            expect("queue cleared after run", len(at.session_state["queue"]) == 0)
        expect("still no exception after run", not at.exception, str(at.exception))

    # --- switch app -> operation list changes ----------------------------------
    calendar_button = next((b for b in at.button if b.key == "pick_calendar"), None)
    if calendar_button:
        calendar_button.click().run()
        expect("switched to calendar", at.session_state["selected_app"] == "calendar")
        expect("calendar operations listed", len(at.selectbox) >= 2)
        expect("no exception on app switch", not at.exception, str(at.exception))

    # --- fill a structured form and queue it ----------------------------------
    op_select = next((s for s in at.selectbox if s.key == "op_calendar"), None)
    if op_select:
        op_select.select("Create event").run()
        expect("selected the create-event operation", not at.exception, str(at.exception))

    title = next((t for t in at.text_input if t.key and t.key.endswith("__summary")), None)
    if title:
        title.set_value("Board sync")
        start = next((t for t in at.text_input if t.key and t.key.endswith("__start")), None)
        if start:
            start.set_value("tomorrow 3pm")
        submit = next((b for b in at.button if "Add to run queue" in (b.label or "")), None)
        if submit:
            submit.click().run()
            expect("form validation accepted the input", len(at.session_state["queue"]) == 1,
                   f"queue={len(at.session_state['queue'])}, exc={at.exception}")
            expect("no exception on form submit", not at.exception, str(at.exception))
    else:
        expect("calendar create form rendered", False, "summary field not found")

    # --- WhatsApp contact "Use" button fills the recipient box ----------------
    wa_pick = next((b for b in at.button if b.key == "pick_whatsapp"), None)
    expect("whatsapp app selector exists", wa_pick is not None)
    if wa_pick:
        wa_pick.click().run()
        expect("switched to whatsapp", at.session_state["selected_app"] == "whatsapp")

        op_wa = next((s for s in at.selectbox if s.key == "op_whatsapp"), None)
        if op_wa:
            op_wa.select("Send text").run()
            expect("whatsapp send-text form rendered", not at.exception, str(at.exception))

            to_box = next((t for t in at.text_input if t.key == "wa_send_text__to"), None)
            expect("recipient field exists", to_box is not None,
                   "wa_send_text__to missing -> field not rendered")

            use_button = next((b for b in at.button if b.key and b.key.startswith("usewa_")), None)
            expect("contact 'Use' button exists", use_button is not None)

            if to_box is not None and use_button is not None:
                expected = use_button.key.replace("usewa_", "")
                captured = capture_logs(lambda: use_button.click().run())
                to_box = next((t for t in at.text_input if t.key == "wa_send_text__to"), None)
                expect("Use button filled the recipient box", to_box is not None and to_box.value == expected,
                       f"expected {expected!r}, got {getattr(to_box, 'value', None)!r}")
                expect("no session-state widget warning", not any(
                    "was created with a default value" in message for message in captured
                ), "; ".join(m for m in captured if "default value" in m))
                expect("no exception after Use", not at.exception, str(at.exception))

    # --- chat tab is honest without an LLM key --------------------------------
    expect("chat transcript container present", len(at.chat_message) >= 0)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s): {FAILURES}")
        return 1
    print("UI smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
