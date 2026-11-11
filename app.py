"""Nexus Ops Grid — a LangGraph multi-agent control surface for Gmail, Google
Calendar, Jira and WhatsApp.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import streamlit as st

import config
from operations import OPS_BY_APP, OPERATIONS, get_operation, groups_for, hidden_defaults, visible_fields
from ui.components import (
    APP_ORDER,
    app_cards,
    empty_queue,
    hero,
    how_it_works,
    missing_banner,
    queue_row,
    render_field,
    report_panel,
    validate,
    _with_value,
)
from ui.theme import esc, footer, inject, pill, section

st.set_page_config(
    page_title="Nexus Ops Grid",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject()

try:
    from agents.graph import run_plan
except Exception as exc:  # missing dependency or bad env
    st.error("Could not boot the agent runtime. Run `pip install -r requirements.txt` and reload.")
    st.exception(exc)
    st.stop()


# --------------------------------------------------------------------------- #
# presets - one click queues a ready-made run
# --------------------------------------------------------------------------- #
PRESETS: list[tuple[str, list[dict]]] = [
    ("✉ Recent mail", [
        {"app": "gmail", "operation_id": "gmail_list", "label": "List recent mail",
         "args": {"max_results": 5}},
    ]),
    ("◷ Book a review", [
        {"app": "calendar", "operation_id": "cal_create_event", "label": "Create event",
         "args": {"summary": "Design review", "start": "tomorrow 15:00", "duration_minutes": 45,
                  "attendees": "ada@example.com", "description": "Walk through the Q4 deck.",
                  "add_meet": True}},
    ]),
    ("◆ File a bug", [
        {"app": "jira", "operation_id": "jira_create_issue", "label": "Create issue",
         "args": {"summary": "Checkout latency spike", "project_key": config.JIRA_DEFAULT_PROJECT or "OPS",
                  "issue_type": "Bug", "priority": "High", "labels": "sev2, checkout"}},
    ]),
    ("◉ WhatsApp alert", [
        {"app": "whatsapp", "operation_id": "wa_send_text", "label": "Send text",
         "args": {"to": config.WHATSAPP_DEFAULT_TO or "919876543210",
                  "body": "Deploy finished — all green ✅"}},
    ]),
    ("◈ All four at once", [
        {"app": "gmail", "operation_id": "gmail_list", "label": "List recent mail", "args": {"max_results": 3}},
        {"app": "calendar", "operation_id": "cal_list_events", "label": "List events", "args": {"max_results": 3}},
        {"app": "jira", "operation_id": "jira_projects", "label": "List projects", "args": {"limit": 5}},
        {"app": "whatsapp", "operation_id": "wa_list_templates", "label": "List templates", "args": {"limit": 5}},
    ]),
]

# --------------------------------------------------------------------------- #
# session
# --------------------------------------------------------------------------- #
def init_state() -> None:
    defaults = {
        "queue": [],
        "selected_app": "gmail",
        "last_run": None,
        "runs": [],
        "chat": [],
        "sim_mode": config.SIMULATE_MODE,
        "wa_contacts": [],
        "wa_to_prefill": "",
        "wa_search": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    # Load persisted contacts if not loaded or if out of sync
    try:
        import json, os
        path = os.path.join(os.path.dirname(__file__), "wa_contacts.json")
        if "wa_contacts_loaded" not in st.session_state:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Ensure uniqueness by normalized phone number
                        seen = set()
                        unique_contacts = []
                        for item in data:
                            num = str(item.get("number", "")).strip()
                            if num and num not in seen:
                                seen.add(num)
                                unique_contacts.append(item)
                        st.session_state["wa_contacts"] = unique_contacts
            st.session_state["wa_contacts_loaded"] = True
    except Exception:
        st.session_state["wa_contacts_loaded"] = True


def _save_wa_contacts(contacts: list[dict]) -> None:
    # Deduplicate preserving last or existing
    seen = set()
    cleaned = []
    for item in contacts:
        num = str(item.get("number", "")).strip()
        if num and num not in seen:
            seen.add(num)
            cleaned.append(item)
    st.session_state["wa_contacts"] = cleaned
    try:
        import json, os
        path = os.path.join(os.path.dirname(__file__), "wa_contacts.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def now_label() -> str:
    return datetime.now().strftime("%d %b · %H:%M:%S")


def add_to_queue(tasks: list[dict]) -> None:
    for task in tasks:
        st.session_state.queue.append({
            **task,
            "id": task.get("id") or uuid.uuid4().hex[:8],
            "approved": bool(task.get("approved", False)),
        })


def pdf_intake() -> None:
    """Upload a PDF, have the planner produce a reviewable queue, never execute it."""
    section(
        "PDF task intake",
        "Upload a PDF of Gmail, Calendar, Jira or WhatsApp instructions. The agents turn it into concrete "
        "actions — anything they are unsure about waits for your approval.",
    )
    upload = st.file_uploader("Instruction PDF", type=["pdf"], key="pdf_task_upload")
    if not upload:
        if st.session_state.get("pdf_notice"):
            st.info(st.session_state.pop("pdf_notice"))
        for warning in st.session_state.get("pdf_warnings") or []:
            st.warning(warning, icon="⚠️")
        st.session_state.pop("pdf_warnings", None)
        return
    st.caption(f"{upload.name} · {upload.size / 1024:.1f} KB · Planning never executes a task by itself.")

    if st.button("Extract and plan PDF tasks", type="primary", key="plan_pdf_tasks"):
        if not config.llm_configured():
            st.error(
                "PDF planning requires an LLM. Configure LLM_PROVIDER plus a key in .env "
                "(GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY or GOOGLE_API_KEY)."
            )
            return
        from agents.pdf_planner import plan_pdf_tasks

        with st.status("Reading the PDF and planning actions…", expanded=True) as status:
            try:
                plan = plan_pdf_tasks(upload.getvalue(), upload.name)
            except Exception as exc:
                status.update(label="Could not plan this PDF", state="error")
                st.error(str(exc))
                return
            tasks = plan["tasks"]
            reviewed = 0
            for task in tasks:
                operation = get_operation(task.get("operation_id", ""))
                # The planner decides when it is unsure. Independently force review
                # whenever a required input is still blank - such a task cannot run.
                missing = (
                    validate(operation, task.get("args") or {}) if operation is not None else []
                )
                if missing:
                    task["approval_required"] = True
                    task["review_reason"] = task.get("review_reason") or (
                        "Missing required input(s): " + ", ".join(
                            field.label for field in (operation.required_fields if operation else [])
                            if not str((task.get("args") or {}).get(field.name, "")).strip()
                        )
                    )
                if task.get("approval_required"):
                    reviewed += 1
                task["approved"] = False
            add_to_queue(tasks)
            status.update(label=f"Prepared {len(tasks)} task(s)", state="complete")

        st.session_state["pdf_notice"] = (
            f"Read {plan['page_count']} page(s) in {plan['chunks']} part(s) and planned {len(tasks)} action(s). "
            f"{reviewed} need your approval; the rest are ready to run."
        )
        if plan.get("failed_parts"):
            st.session_state["pdf_warnings"] = plan["failed_parts"]
        st.rerun()


# --------------------------------------------------------------------------- #
# sidebar
# --------------------------------------------------------------------------- #
def sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="nx-brand"><div class="nx-mark">◈</div><span>Nexus Ops</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="nx-side-title" style="margin-top:18px">Execution mode</div>', unsafe_allow_html=True)
        mode = st.radio(
            "Execution mode", ("auto", "always", "never"), index=("auto", "always", "never").index(config.SIMULATE_MODE),
            key="sim_mode_widget", horizontal=True, label_visibility="collapsed",
            help="auto: simulate only apps without credentials · always: never call a real API · "
                 "never: always call the live API",
        )
        config.SIMULATE_MODE = mode

        st.markdown('<div class="nx-side-title" style="margin-top:22px">Agent fleet</div>', unsafe_allow_html=True)
        for status in config.status_snapshot():
            tone = "live" if status.configured else "sim"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:7px 0;border-bottom:1px solid rgba(130,150,255,.09)">'
                f'<span style="font-size:.84rem"><span style="color:{status.accent}">{status.icon}</span> '
                f'{esc(status.label)}</span>{pill(status.mode, tone)}</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="nx-side-title" style="margin-top:22px">Model</div>', unsafe_allow_html=True)
        if config.llm_configured():
            st.markdown(f"`{config.LLM_PROVIDER}` · `{config.model_name()}`")
        else:
            st.markdown('<span class="nx-pill sim"><span class="nx-dot"></span>not configured</span>',
                        unsafe_allow_html=True)
            st.caption("Command Deck works without a model. A key enables PDF planning.")

        st.markdown('<div class="nx-side-title" style="margin-top:22px">Surface</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="display:flex;gap:14px;font-size:.78rem;color:#9aa2c6">'
            f'<span>{len(OPERATIONS)} operations</span><span>{len(st.session_state.queue)} queued</span>'
            f'<span>{len(st.session_state.runs)} runs</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Timezone · {config.DEFAULT_TIMEZONE}")

        st.markdown("")
        col_a, col_b = st.columns(2)
        if col_a.button("Clear queue", use_container_width=True, disabled=not st.session_state.queue):
            st.session_state.queue = []
            st.rerun()
        if col_b.button("Reset session", use_container_width=True):
            for key in ("queue", "last_run", "runs", "chat"):
                st.session_state[key] = [] if key != "last_run" else None
            st.rerun()

        with st.expander("Setup checklist"):
            st.markdown(
                "1. `pip install -r requirements.txt`\n"
                "2. Copy `.env.example` → `.env` and fill what you have\n"
                "3. `python scripts/google_auth.py` for Gmail + Calendar\n"
                "4. `streamlit run app.py`"
            )


# --------------------------------------------------------------------------- #
# command deck
# --------------------------------------------------------------------------- #
def preset_row() -> None:
    section("Quick starts", "One click queues a ready-made run — then press Execute.")
    columns = st.columns(len(PRESETS))
    for column, (label, tasks) in zip(columns, PRESETS):
        if column.button(label, key=f"preset_{label}", use_container_width=True):
            add_to_queue(tasks)
            st.rerun()


def choose_app() -> str:
    current = st.session_state.selected_app
    columns = st.columns(4, gap="small")
    for column, app in zip(columns, APP_ORDER):
        meta = config.APP_META[app]
        active = app == current
        if column.button(
            f"{meta['icon']}  {meta['label']}",
            key=f"pick_{app}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state.selected_app = app
            st.rerun()
    return st.session_state.selected_app


def operation_builder() -> None:
    app = choose_app()
    operations = OPS_BY_APP.get(app, [])
    if not operations:
        st.info("No operations registered for this app.")
        return

    if app == "whatsapp":
        with st.expander("Saved WhatsApp contacts", expanded=False):
            st.session_state["wa_search"] = st.text_input("Search by name", value=st.session_state.get("wa_search", ""), key="wa_search_bar")
            contacts = st.session_state.get("wa_contacts", [])
            search = (st.session_state.get("wa_search") or "").lower().strip()
            if search:
                contacts = [c for c in contacts if search in str(c.get('name','')).lower()]
            if contacts:
                for idx, c in enumerate(contacts):
                    c1, c2, c3, c4 = st.columns([0.46, 0.18, 0.18, 0.18])
                    with c1:
                        st.text(f"{c.get('name')} - {c.get('number')}")
                    with c2:
                        if st.button("Use", key=f"usewa_{idx}_{c.get('number')}"):
                            # Hand the number to the recipient field of whichever
                            # WhatsApp operation is open. The field picks this up as
                            # a one-shot prefill on this same run, so the number lands
                            # in the To box without touching widget keys directly
                            # (which caused the Session State warning).
                            st.session_state["wa_to_prefill"] = str(c.get("number"))
                            st.toast(f"Recipient set · {c.get('name')} · {c.get('number')}", icon="✅")
                    with c3:
                        if st.button("Edit", key=f"editwa_{idx}_{c.get('number')}"):
                            st.session_state["wa_edit_num"] = c.get('number')
                            st.session_state["wa_edit_name"] = c.get('name')
                            st.rerun()
                    with c4:
                        if st.button("Delete", key=f"delwa_{idx}_{c.get('number')}"):
                            contacts_all = st.session_state.get("wa_contacts", [])
                            contacts_all = [x for x in contacts_all if str(x.get('number','')).strip() != str(c.get('number','')).strip()]
                            _save_wa_contacts(contacts_all)
                            if st.session_state.get("wa_edit_num") == c.get('number'):
                                st.session_state.pop("wa_edit_num", None)
                                st.session_state.pop("wa_edit_name", None)
                            st.toast(f"Deleted contact {c.get('name')}", icon="🗑️")
                            st.rerun()
            if st.session_state.get("wa_edit_num"):
                e_name = st.text_input("Edit name", value=st.session_state.get("wa_edit_name",""), key="wa_edit_name_in")
                e_num = st.text_input("Edit number", value=st.session_state.get("wa_edit_num",""), key="wa_edit_num_in")
                ec1, ec2 = st.columns(2)
                if ec1.button("Update", key="wa_edit_update"):
                    contacts_all = st.session_state.get("wa_contacts", [])
                    old = str(st.session_state.get("wa_edit_num", "")).strip()
                    # Remove old and remove if existing new number to prevent duplicates
                    contacts_all = [x for x in contacts_all if str(x.get('number','')).strip() not in (old, e_num.strip())]
                    contacts_all.append({"name": e_name.strip(), "number": e_num.strip()})
                    _save_wa_contacts(contacts_all)
                    st.session_state.pop("wa_edit_num", None)
                    st.session_state.pop("wa_edit_name", None)
                    st.rerun()
                if ec2.button("Cancel", key="wa_edit_cancel"):
                    st.session_state.pop("wa_edit_num", None)
                    st.session_state.pop("wa_edit_name", None)
                    st.rerun()
            if "wa_contact_name" not in st.session_state:
                st.session_state["wa_contact_name"] = ""
            if "wa_contact_num" not in st.session_state:
                st.session_state["wa_contact_num"] = ""
            c_name = st.text_input("Contact name", key="wa_contact_name")
            c_num = st.text_input("Phone number (digits with country code)", key="wa_contact_num")
            if st.button("Save contact", key="wa_save_contact"):
                if c_name and c_num:
                    clean_num = c_num.strip()
                    contacts_all = st.session_state.get("wa_contacts", [])
                    # Enforce uniqueness: replace existing entry if same number
                    contacts_all = [x for x in contacts_all if str(x.get('number','')).strip() != clean_num]
                    contacts_all.append({"name": c_name.strip(), "number": clean_num})
                    _save_wa_contacts(contacts_all)
                    st.session_state.pop("wa_contact_name", None)
                    st.session_state.pop("wa_contact_num", None)
                    st.rerun()

    group_options = ["All"] + groups_for(app)
    group_col, op_col = st.columns([0.32, 0.68])
    group = group_col.selectbox("Group", group_options, key=f"grp_{app}")
    visible = [o for o in operations if group == "All" or o.group == group]
    names = [o.name for o in visible]
    chosen_name = op_col.selectbox("Operation", names, key=f"op_{app}")
    operation = visible[names.index(chosen_name)]

    st.markdown(
        f'<div class="nx-card" style="--glow:rgba(34,211,238,.12);padding:14px 16px;margin:6px 0 14px">'
        f'<div style="font-size:.86rem;color:#d6dbfb">{esc(operation.summary)}</div>'
        f'<div class="nx-mono" style="margin-top:6px">{esc(operation.app)} · {esc(operation.group)} · '
        f'<span style="color:#8ee7ff">{esc(operation.tool)}</span></div>'
        + ('<div class="nx-res-sub" style="margin-top:8px">Or describe it in a PDF above and let the agents plan it</div>'
           if operation.example else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    values: dict = {}
    hidden = hidden_defaults(operation)
    if hidden:
        st.caption(
            "Runs against your **primary calendar**. "
            f"(Hidden field: {', '.join(f'`{k}={v}`' for k, v in hidden.items())}.)"
        )
    with st.form(key=f"form_{operation.id}", clear_on_submit=False, border=False):
        buffer: list = []

        def flush() -> None:
            if not buffer:
                return
            columns = st.columns(len(buffer))
            for column, field in zip(columns, buffer):
                with column:
                    values[field.name] = render_field(field, operation.id)
            buffer.clear()

        for field in visible_fields(operation):
            if field.kind in ("textarea", "json", "file", "datetime"):
                flush()
                values[field.name] = render_field(field, operation.id)
            else:
                buffer.append(field)
                if len(buffer) == 2:
                    flush()
        flush()

        if not visible_fields(operation):
            st.caption("This operation needs no inputs.")

        submitted = st.form_submit_button("＋  Add to run queue", type="primary", use_container_width=True)

    if submitted:
        # Hidden fields fall back to their documented default.
        values.update(hidden_defaults(operation))
        problems = validate(operation, values)
        if problems:
            for problem in problems:
                st.error(problem)
        else:
            args = {
                key: value for key, value in values.items()
                if not (isinstance(value, str) and not value.strip())
            }
            add_to_queue([{
                "app": app,
                "operation_id": operation.id,
                "label": operation.name,
                "args": args,
            }])
            st.toast(f"Queued · {operation.name}", icon="✅")
            st.rerun()


def render_queue() -> None:
    queue = st.session_state.queue
    pending_review = [task for task in queue if task.get("approval_required") and not task.get("approved")]
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
        f'<span class="nx-mono" style="letter-spacing:.24em;color:#c3c9ef">RUN QUEUE</span>'
        f'<span class="nx-mono">{len(queue)} queued</span></div>',
        unsafe_allow_html=True,
    )
    if not queue:
        empty_queue()
    else:
        for index, task in enumerate(queue):
            queue_row(task, index)

    if pending_review:
        st.warning(f"{len(pending_review)} task(s) need human approval and will not run yet.", icon="⚠️")
        with st.expander("Human approval · review and edit pending tasks", expanded=True):
            for task in pending_review:
                operation = get_operation(task.get("operation_id", ""))
                st.markdown(
                    f"**{task.get('label', 'Task')}** · "
                    f"{config.APP_META.get(task.get('app'), {}).get('label', task.get('app'))}"
                )
                st.caption(task.get("review_reason") or "Confirm or correct this action before it can run.")
                source = task.get("source") or {}
                if source.get("filename"):
                    st.caption(
                        f"From {source['filename']} · part {source.get('part', '?')} "
                        f"of {source.get('page_count', '?')} page(s)"
                    )

                if operation is None:
                    st.info("This task requires free-form agent execution. Approve only if its instruction is correct.")
                    loaded = list(task.get("args") or {})
                    if loaded:
                        st.caption("Provided values: " + ", ".join(loaded))
                    task["prompt"] = st.text_area(
                        "Instruction", value=task.get("prompt", ""), key=f"review_prompt_{task['id']}"
                    )
                else:
                    # Real inputs instead of raw JSON, so a non-technical reviewer can fix them.
                    edited_args: dict[str, Any] = {}
                    for field in operation.fields:
                        hint = ""
                        current = task.get("args", {}).get(field.name)
                        if field.required and (current in (None, "")):
                            hint = " ← required, currently blank"
                        widget = render_field(
                            _with_value(field, current), f"review_{task['id']}"
                        )
                        edited_args[field.name] = widget
                        if hint:
                            st.caption(f"**{field.label}**{hint}")
                    task["args"] = {
                        key: value for key, value in edited_args.items()
                        if not (isinstance(value, str) and not value.strip())
                    }
                    problems = validate(operation, task["args"])
                    if problems:
                        st.error("Still missing before it can run: " + " ".join(problems))

                approve, remove = st.columns(2)
                blocked = operation is not None and bool(validate(operation, task.get("args") or {}))
                if approve.button(
                    "Approve task", key=f"approve_{task['id']}", type="primary",
                    use_container_width=True, disabled=blocked,
                    help="Fill the required fields first." if blocked else "Allow this task to run.",
                ):
                    task["approval_required"] = True
                    task["approved"] = True
                    st.rerun()
                if remove.button("Remove task", key=f"review_remove_{task['id']}", use_container_width=True):
                    st.session_state.queue = [item for item in st.session_state.queue if item["id"] != task["id"]]
                    st.rerun()
                st.divider()

    st.markdown("")
    run_col, clear_col = st.columns([1.6, 1])
    executable = [task for task in queue if not task.get("approval_required") or task.get("approved")]
    if run_col.button("▶  Execute approved queue", type="primary", use_container_width=True, disabled=not executable):
        execute_queue()
    if clear_col.button("Clear", use_container_width=True, disabled=not queue):
        st.session_state.queue = []
        st.rerun()

    st.caption("Tasks run in one LangGraph superstep — all four agents can work at the same time.")


def execute_queue() -> None:
    # Approval-gated tasks stay visible in the queue but cannot reach any tool.
    tasks = [
        task for task in st.session_state.queue
        if not task.get("approval_required") or task.get("approved")
    ]
    if not tasks:
        st.warning("Approve at least one queued task before executing.")
        return
    with st.status(f"Dispatching {len(tasks)} task(s) to the agent grid…", expanded=True) as status:
        st.write("Supervisor → " + "  ·  ".join(
            f"{config.APP_META[t['app']]['icon']} {config.APP_META[t['app']]['label']}" for t in tasks
        ))
        try:
            state = run_plan(tasks)
        except Exception as exc:
            status.update(label="Run failed", state="error")
            st.exception(exc)
            return
        status.update(label="Agents finished — report below", state="complete")

    st.session_state.last_run = state
    st.session_state.runs.insert(0, {
        "ts": now_label(),
        "mode": "structured",
        "prompt": " · ".join(t["label"] for t in tasks),
        "state": state,
    })
    # Only drop what actually ran - tasks still awaiting approval stay queued.
    ran_ids = {task.get("id") for task in tasks}
    st.session_state.queue = [t for t in st.session_state.queue if t.get("id") not in ran_ids]
    st.rerun()


def command_deck() -> None:
    pdf_intake()
    section("Command deck", "Choose the app, pick the operation, fill the required fields (marked *).")
    preset_row()

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        with st.container(border=True):
            operation_builder()
    with right:
        with st.container(border=True):
            render_queue()

    last = st.session_state.last_run
    if last:
        section("Execution report", "What the agents did, and the raw payload each tool returned.")
        report_panel(last)


# --------------------------------------------------------------------------- #
# run log
# --------------------------------------------------------------------------- #
def run_log() -> None:
    section("Run log", "Every execution this session, newest first.")
    runs = st.session_state.runs
    if not runs:
        st.markdown('<div class="nx-empty">No runs yet this session.</div>', unsafe_allow_html=True)
        return

    for run in runs[:25]:
        results = run["state"].get("results") or []
        ok = sum(1 for r in results if r.get("status") == "success")
        with st.expander(f"{run['ts']} · {run['mode']} · {run['prompt'][:70]} · {ok}/{len(results)} ok"):
            st.markdown(run["state"].get("answer") or "—")
            if results:
                st.json([
                    {k: r.get(k) for k in ("app", "label", "status", "ms", "summary", "error")} for r in results
                ], expanded=False)

    st.download_button(
        "Download session log (JSON)",
        data=json.dumps(st.session_state.runs, indent=2, default=str),
        file_name="nexus-run-log.json",
        mime="application/json",
    )


# --------------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------------- #
init_state()
sidebar()
hero()
missing_banner()

section("Agent fleet", "Four specialists, each with its own toolbelt.")
app_cards()

tabs = st.tabs(["⚡ Command Deck", "🧾 Run Log", "📚 How it works"])
with tabs[0]:
    command_deck()
with tabs[1]:
    run_log()
with tabs[2]:
    how_it_works()

footer()
