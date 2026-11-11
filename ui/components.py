"""Reusable UI pieces: hero, app grid, dynamic forms, queue, result cards."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time, timedelta
import json
from pathlib import Path
import re
import tempfile
from typing import Any

import streamlit as st

import config
from operations import Field, Operation, OPS_BY_APP, OPERATIONS
from ui.theme import esc, pill, section

APP_ORDER = ("gmail", "calendar", "jira", "whatsapp")


# --------------------------------------------------------------------------- #
# hero + status
# --------------------------------------------------------------------------- #
def hero() -> None:
    st.markdown(
        '<div class="nx-hero">'
        '<div class="nx-eyebrow">LangGraph · multi-agent operations grid</div>'
        '<div class="nx-title">One command surface for<br/>Gmail · Calendar · Jira · WhatsApp</div>'
        '<div class="nx-sub">Four specialist agents, one supervisor. Pick an app, choose an operation, '
        'fill the fields — the graph fans the work out to the right agent in parallel and reports back. '
        'Or just describe what you want in plain English.</div>'
        '<div class="nx-steps">'
        '<div class="nx-step"><b>01</b> Choose app</div>'
        '<div class="nx-step"><b>02</b> Choose operation</div>'
        '<div class="nx-step"><b>03</b> Fill values</div>'
        '<div class="nx-step"><b>04</b> Agents execute</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def app_cards() -> None:
    statuses = {s.app: s for s in config.status_snapshot()}
    columns = st.columns(4, gap="medium")
    for column, app in zip(columns, APP_ORDER):
        meta = config.APP_META[app]
        status = statuses[app]
        tone = "live" if status.mode == "LIVE" else "sim"
        count = len(OPS_BY_APP.get(app, []))
        with column:
            st.markdown(
                f'<div class="nx-card" style="--accent:{meta["accent"]};--glow:{meta["accent"]}33;">'
                f'<div class="nx-app-top"><div class="nx-app-icon">{meta["icon"]}</div>'
                f'<div><div class="nx-app-name">{esc(meta["label"])}</div>'
                f'<div class="nx-app-sub">{esc(meta["tagline"])}</div></div></div>'
                f'<div class="nx-app-foot"><span>{count} operations</span>{pill(status.mode, tone)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------- #
# dynamic form
# --------------------------------------------------------------------------- #
def _with_value(field: Field, value: Any) -> Field:
    """Return a copy of a field with its current value as the default."""
    return replace(field, default=value)


def render_field(field: Field, prefix: str) -> Any:
    key = f"{prefix}__{field.name}"
    label = f"{field.label} *" if field.required else field.label
    help_text = field.help or None
    default = field.default

    if field.kind == "toggle":
        return st.toggle(label, value=bool(default), key=key, help=help_text)

    # Multi-select dropdown
    if field.kind == "multiselect":
        options = list(field.options)
        default_list = []
        if default:
            if isinstance(default, (list, tuple)):
                default_list = [d for d in default if d in options]
            elif isinstance(default, str):
                default_list = [d.strip() for d in default.split(",") if d.strip() in options]
        chosen = st.multiselect(label, options, default=default_list, key=key, help=help_text)
        return ", ".join(chosen)

    # Date-only picker (Calendar)
    if field.kind == "date":
        init_date = None
        if default:
            if isinstance(default, date):
                init_date = default
            elif isinstance(default, str) and default.strip():
                try:
                    init_date = date.fromisoformat(default.strip()[:10])
                except Exception:
                    init_date = date.today()
        elif field.required:
            init_date = date.today()

        chosen_date = st.date_input(
            label,
            value=init_date,
            key=key,
            help=help_text or "Click to choose date from calendar",
            format="YYYY-MM-DD",
        )
        if chosen_date is None:
            return ""
        return chosen_date.strftime("%Y-%m-%d")

    # Date & Time picker (Interactive calendar + scrollable clock timing)
    if field.kind == "datetime":
        raw_hint = f"{default or ''} {field.placeholder or ''}".lower()
        if field.required or default:
            if "tomorrow" in raw_hint:
                init_d = date.today() + timedelta(days=1)
            else:
                init_d = date.today()

            t_match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw_hint)
            if t_match:
                init_t = time(int(t_match.group(1)), int(t_match.group(2)))
            elif "3pm" in raw_hint or "15" in raw_hint:
                init_t = time(15, 0)
            elif "9am" in raw_hint or "09" in raw_hint:
                init_t = time(9, 0)
            elif "11am" in raw_hint or "11:00" in raw_hint:
                init_t = time(11, 0)
            elif "4pm" in raw_hint or "16" in raw_hint:
                init_t = time(16, 0)
            else:
                init_t = time(10, 0)
        else:
            init_d = None
            init_t = time(10, 0)

        col_d, col_t = st.columns([1.15, 0.85])
        with col_d:
            chosen_d = st.date_input(
                f"📅 {label} · Date",
                value=init_d,
                key=f"{key}__date",
                help=help_text or "Click to open calendar",
                format="YYYY-MM-DD",
            )
        with col_t:
            chosen_t = st.time_input(
                f"◷ {label} · Time",
                value=init_t,
                step=timedelta(minutes=15),
                key=f"{key}__time",
                help="Scroll up/down or pick clock timing",
            )

        if chosen_d is None:
            return ""
        t_str = chosen_t.strftime("%H:%M:%S") if chosen_t is not None else "09:00:00"
        return f"{chosen_d.strftime('%Y-%m-%d')} {t_str}"

    # Dropdown select (or fields with options)
    if field.kind == "select" or (field.options and field.kind in ("text", "number")):
        options = list(field.options)
        index = options.index(default) if default in options else 0

        def _formatter(val: Any) -> str:
            if field.name == "recurrence":
                recur_map = {
                    "": "Does not repeat (One-off event)",
                    "RRULE:FREQ=DAILY": "Daily",
                    "RRULE:FREQ=WEEKLY": "Weekly (same day)",
                    "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR": "Every weekday (Mon - Fri)",
                    "RRULE:FREQ=MONTHLY": "Monthly",
                    "RRULE:FREQ=YEARLY": "Yearly",
                }
                return recur_map.get(str(val), str(val))
            if field.name == "timezone_name":
                if not val:
                    return f"Default ({getattr(config, 'DEFAULT_TIMEZONE', 'Asia/Kolkata')})"
                return str(val)
            if field.name == "label":
                if not val:
                    return "All mail (no label filter)"
                return str(val)
            if field.name == "reminders_minutes":
                remind_map = {
                    -1: "Keep existing reminder (-1)",
                    0: "At time of event (0 min)",
                    5: "5 minutes before",
                    10: "10 minutes before",
                    15: "15 minutes before",
                    30: "30 minutes before",
                    60: "1 hour before",
                    120: "2 hours before",
                    1440: "1 day before",
                }
                return remind_map.get(val, f"{val} minutes before")
            if field.name == "duration_minutes":
                dur_map = {
                    15: "15 minutes",
                    30: "30 minutes",
                    45: "45 minutes",
                    60: "1 hour (60 min)",
                    90: "1.5 hours (90 min)",
                    120: "2 hours (120 min)",
                    180: "3 hours (180 min)",
                    240: "4 hours (240 min)",
                    480: "Full day (8 hours)",
                }
                return dur_map.get(val, f"{val} minutes")
            if field.name in ("work_start_hour", "work_end_hour"):
                try:
                    h = int(val)
                    am_pm = "AM" if h < 12 else "PM"
                    h12 = h % 12 or 12
                    return f"{h12}:00 {am_pm} ({h}:00)"
                except Exception:
                    return str(val)
            if field.name == "state":
                state_map = {
                    "active,future": "Active & Future sprints",
                    "active": "Active sprints only",
                    "future": "Future sprints only",
                    "closed": "Closed sprints only",
                }
                return state_map.get(str(val), str(val))
            return str(val)

        return st.selectbox(label, options, index=index, format_func=_formatter, key=key, help=help_text)

    if field.kind == "number":
        value = default if default is not None else 0
        if isinstance(value, float):
            return st.number_input(label, value=float(value), step=1.0, format="%.6f", key=key, help=help_text)
        return st.number_input(label, value=int(value), step=1, key=key, help=help_text)
    if field.kind == "textarea":
        return st.text_area(label, value="" if default is None else str(default), key=key,
                            placeholder=field.placeholder, help=help_text, height=132)
    if field.kind == "json":
        return st.text_area(label, value="" if default is None else str(default), key=key,
                            placeholder=field.placeholder, help=help_text, height=120)
    if field.kind == "file":
        path = st.text_input(label, value="" if default is None else str(default), key=key,
                             placeholder=field.placeholder, help=help_text)
        upload = st.file_uploader("…or upload a file", key=f"{key}__upload", label_visibility="collapsed")
        if upload is not None:
            target = Path(tempfile.gettempdir()) / "nexus_uploads" / upload.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(upload.getbuffer())
            st.caption(f"Using uploaded file: `{target}`")
            return str(target)
        return path
    # Make Jira project key non-editable - never allow editing
    if field.name == "project_key":
        val = "" if default is None else str(default)
        if not val and hasattr(config, 'JIRA_DEFAULT_PROJECT') and config.JIRA_DEFAULT_PROJECT:
            val = str(config.JIRA_DEFAULT_PROJECT)
        st.text_input(label, value=val, key=key, placeholder=field.placeholder, help=help_text, disabled=True)
        return val
    # Prefill WhatsApp recipient ONLY if user clicked "Use" on a saved contact.
    if field.name == "to" and prefix.startswith("wa_"):
        pending = st.session_state.pop("wa_to_prefill", None)
        if pending not in (None, ""):
            st.session_state[key] = str(pending)
        return st.text_input(label, key=key, placeholder=field.placeholder, help=help_text)

    # Everything else (plain text, csv, anything unrecognised) -> single-line input.
    return st.text_input(label, value="" if default is None else str(default), key=key,
                         placeholder=field.placeholder, help=help_text)


def validate(operation: Operation, args: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in operation.fields:
        value = args.get(field.name)
        blank = value is None or (isinstance(value, str) and not value.strip())
        if field.required and blank:
            problems.append(f"**{field.label}** is required.")
        if field.kind == "json" and isinstance(value, str) and value.strip():
            try:
                json.loads(value)
            except json.JSONDecodeError as exc:
                problems.append(f"**{field.label}** is not valid JSON ({exc.msg}, char {exc.pos}).")
    return problems


# --------------------------------------------------------------------------- #
# queue
# --------------------------------------------------------------------------- #
def queue_row(task: dict[str, Any], index: int) -> None:
    meta = config.APP_META.get(task["app"], {"icon": "•", "label": task["app"], "accent": "#7c6cff"})
    args = task.get("args") or {}
    preview = " · ".join(f"{k}={str(v)[:24]}" for k, v in list(args.items())[:3]) or "no parameters"
    left, right = st.columns([0.86, 0.14], vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="nx-q" style="--accent:{meta["accent"]}">'
            f'<div class="nx-app-icon">{meta["icon"]}</div>'
            f'<div><div class="nx-q-title">{esc(task.get("label", "task"))}</div>'
            f'<div class="nx-q-meta">{esc(meta["label"])} → {esc(preview)}</div></div></div>',
            unsafe_allow_html=True,
        )
    with right:
        if st.button("✕", key=f"rm_{task['id']}_{index}", help="Remove from queue", use_container_width=True):
            st.session_state.queue = [t for t in st.session_state.queue if t["id"] != task["id"]]
            st.rerun()


def empty_queue() -> None:
    st.markdown(
        '<div class="nx-empty">The run queue is empty.<br/>Add an operation on the left — mix apps freely, '
        'they execute <b>in parallel</b>.</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #
def result_card(result: dict[str, Any]) -> None:
    meta = config.APP_META.get(result.get("app", ""), {"icon": "•", "label": result.get("app"), "accent": "#7c6cff"})
    ok = result.get("status") == "success"
    tone = "ok" if ok else "fail"
    detail = result.get("summary") or result.get("error") or "Completed."
    st.markdown(
        f'<div class="nx-res {tone}" style="--accent:{meta["accent"]}">'
        f'<div class="nx-res-top"><div><div class="nx-res-title">'
        f'<span style="color:{meta["accent"]}">{meta["icon"]}</span> {esc(meta["label"])} · {esc(result.get("label"))}'
        f'</div><div class="nx-res-sub">{esc(str(detail)[:400])}</div></div>'
        f'<div class="nx-mono">{"✓" if ok else "✕"} {result.get("status")} · {result.get("ms", 0)} ms'
        f' · {esc(result.get("started_at", ""))}</div></div></div>',
        unsafe_allow_html=True,
    )
    steps = result.get("steps") or []
    with st.expander(f"Trace · {len(steps)} tool call{'s' if len(steps) != 1 else ''}"):
        if result.get("instruction"):
            st.markdown(f"**Instruction** — {result['instruction']}")
        if result.get("args"):
            st.markdown("**Inputs**")
            st.json(result["args"], expanded=False)
        for step in steps:
            tone_mark = "✅" if step.get("ok") else "⛔"
            st.markdown(f"`{step.get('tool')}` · {step.get('ms', 0)} ms · {tone_mark}")
            if step.get("error"):
                st.caption(step["error"])
        st.markdown("**Output**")
        st.json(result.get("output") or {}, expanded=False)


def report_panel(state: dict[str, Any]) -> None:
    results = state.get("results") or []
    answer = state.get("answer") or ""
    if not results and not answer:
        return

    if results:
        ok = sum(1 for r in results if r.get("status") == "success")
        total_ms = sum(int(r.get("ms") or 0) for r in results)
        columns = st.columns(4)
        columns[0].metric("Actions", len(results))
        columns[1].metric("Succeeded", ok)
        columns[2].metric("Failed", len(results) - ok)
        columns[3].metric("Wall time", f"{total_ms / 1000:.1f}s")

    with st.container(border=True):
        st.markdown(answer or "No report.")

    if results:
        section("Agent trace", "Every tool call, its inputs and the raw payload it returned.")
        for result in results:
            result_card(result)


# --------------------------------------------------------------------------- #
# explainers
# --------------------------------------------------------------------------- #
def architecture() -> None:
    st.markdown(
        '<div class="nx-card" style="--glow:rgba(34,211,238,.16)">'
        '<div class="nx-arch">'
        '<div class="nx-arch-col">'
        '<div class="nx-node">🧠 You</div>'
        '<div class="nx-node">Pick operation<br/><span style="color:#5f6790">or type a sentence</span></div>'
        '</div>'
        '<div class="nx-arch-col">'
        '<div class="nx-node hub">Supervisor (LangGraph)</div>'
        '<div class="nx-arrow">↓ Send() fan-out · parallel superstep ↓</div>'
        '<div class="nx-arch-col" style="display:grid;grid-template-columns:1fr 1fr;gap:8px">'
        '<div class="nx-node">✉ Gmail agent</div><div class="nx-node">◷ Calendar agent</div>'
        '<div class="nx-node">◆ Jira agent</div><div class="nx-node">◉ WhatsApp agent</div>'
        '</div>'
        '<div class="nx-arrow">↓ merge results ↓</div>'
        '<div class="nx-node hub">Report + full trace</div>'
        '</div>'
        '<div class="nx-arch-col">'
        '<div class="nx-node">Gmail API</div><div class="nx-node">Calendar API</div>'
        '<div class="nx-node">Jira REST v3</div><div class="nx-node">WhatsApp Cloud API</div>'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def how_it_works() -> None:
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        section("How to drive it", "Three ways in, same agents underneath.")
        st.markdown(
            "**1 · Command Deck (no LLM needed).** Choose an app, choose an operation, fill the fields it asks for, "
            "then *Add to run queue*. Queue several actions — even across different apps — and hit **Execute**. "
            "Every operation maps to exactly one typed tool, so the run is deterministic and auditable.\n\n"
            "**2 · Agent Chat (LLM).** Describe the outcome in a sentence: *“book 30 minutes with ada@example.com "
            "tomorrow afternoon and WhatsApp her the invite”*. The supervisor turns that into tasks, routes each "
            "one to its specialist agent and reports back.\n\n"
            "**3 · Presets.** The chips under the hero queue a ready-made multi-app run so you can watch the "
            "fan-out immediately.\n\n"
            "**Reading the report.** The summary card lists each action with a ✅/⛔ and its key id. Open "
            "*Trace* under a result to see the tool name, the exact arguments that were sent and the raw API "
            "payload returned — nothing is hidden."
        )

        section("What each app covers", f"{len(OPERATIONS)} operations wired to live APIs.")
        rows = []
        for app in APP_ORDER:
            groups = sorted({op.group for op in OPS_BY_APP.get(app, [])})
            rows.append(f"| {config.APP_META[app]['icon']} **{config.APP_META[app]['label']}** "
                        f"| {len(OPS_BY_APP.get(app, []))} | {', '.join(groups)} |")
        st.markdown("| App | Ops | Groups |\n|---|---:|---|\n" + "\n".join(rows))

        section("Go live", "Simulated mode is on until credentials exist.")
        st.code(
            "# 1. Google (Gmail + Calendar, one token)\n"
            "python scripts/google_auth.py\n\n"
            "# 2. Jira Cloud  -> .env\n"
            "JIRA_BASE_URL=https://your-domain.atlassian.net\n"
            "JIRA_EMAIL=you@company.com\n"
            "JIRA_API_TOKEN=...\n\n"
            "# 3. WhatsApp Cloud API -> .env\n"
            "WHATSAPP_TOKEN=EAAG...\n"
            "WHATSAPP_PHONE_NUMBER_ID=1234567890\n"
            "WHATSAPP_BUSINESS_ID=0987654321\n\n"
            "# 4. Optional LLM for chat mode\n"
            "LLM_PROVIDER=openai\n"
            "LLM_MODEL=gpt-4o-mini\n"
            "OPENAI_API_KEY=sk-...",
            language="bash",
        )

    with right:
        section("Graph topology")
        architecture()
        st.markdown("")
        section("Connection status")
        for status in config.status_snapshot():
            with st.expander(f"{status.icon}  {status.label} — {status.mode}"):
                if status.configured:
                    st.markdown("✅ Credentials detected. This app will hit the **live** API.")
                else:
                    st.markdown("⚠️ Running in **simulated** mode. Missing:")
                    for hint in status.hints:
                        st.markdown(f"- `{hint}`")
        st.caption("Simulated mode never calls the network — it returns realistic fixtures so the UI and graph "
                   "stay fully testable. Switch with `SIMULATE_MODE` in `.env`.")


def missing_banner() -> None:
    missing = [s for s in config.status_snapshot() if not s.configured]
    if not missing:
        return
    names = " · ".join(f"{s.icon} {s.label}" for s in missing)
    st.markdown(
        f'<div class="nx-card" style="--glow:rgba(255,196,84,.14);padding:14px 18px">'
        f'<span class="nx-mono">SIMULATION NOTICE</span> &nbsp; '
        f'<span style="font-size:.84rem;color:#c8cdec">{esc(names)} have no credentials yet — those runs return '
        f'simulated payloads. Open <b>How it works → Go live</b> to connect them.</span></div>',
        unsafe_allow_html=True,
    )
