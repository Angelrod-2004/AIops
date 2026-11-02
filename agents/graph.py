"""LangGraph wiring: supervisor -> per-app specialists (in parallel) -> report."""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import config
from agents.core import GraphState, build_llm, execute_task
from operations import OPERATIONS, get_operation
from tools.registry import tool_names

APP_NODES = tuple(config.APPS)


# --------------------------------------------------------------------------- #
# supervisor
# --------------------------------------------------------------------------- #
def _catalog() -> str:
    rows = []
    for operation in OPERATIONS:
        required = ",".join(f.name for f in operation.fields if f.required) or "-"
        rows.append(f"{operation.app} | {operation.id} | {operation.summary} | required: {required}")
    return "\n".join(rows)


PLANNER_PROMPT = """You are the supervisor of a multi-agent operations team with four specialists:
gmail, calendar, jira, whatsapp.

Today is {today} (timezone {tz}).

Catalogue of supported operations (app | operation_id | what it does | required args):
{catalogue}

Split the user's request into one task per concrete action. Allowed task shapes:
1. {{"app": "<one of gmail|calendar|jira|whatsapp>", "operation_id": "<id from the catalogue>",
   "args": {{...exact parameter names from required args...}}, "label": "<short human label>"}}
2. {{"app": "<app>", "operation_id": "auto", "prompt": "<full instruction>", "label": "<short label>"}}
   Use "auto" only when no catalogued operation fits.

Rules:
- Never invent operation ids. Never put a value in args that the user did not provide and you cannot infer.
- Use ISO-8601 datetimes in args, resolved against today's date.
- If the request is a question about data (e.g. "what's on my calendar"), pick the matching read operation.
- If something essential is missing, add it to "missing" instead of guessing.

Return STRICT JSON only, no markdown:
{{"tasks": [...], "missing": ["..."], "reply": "<one sentence describing the plan>"}}"""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("planner did not return JSON")
    return json.loads(cleaned[start : end + 1])


def tasks_from_payload(payload: dict[str, Any], prompt: str) -> tuple[list[dict[str, Any]], str]:
    """Validate a planner payload against the catalogue (pure, unit-testable)."""
    tasks: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("tasks") or [], start=1):
        if not isinstance(raw, dict):
            continue
        app = str(raw.get("app", "")).strip().lower()
        if app not in config.APPS:
            continue
        op_id = str(raw.get("operation_id") or "auto").strip()
        operation = get_operation(op_id)
        if operation is not None and operation.app != app:
            # trust the catalogue over the planner
            app = operation.app
            op_id = operation.id
        if operation is None and op_id != "auto":
            op_id = "auto"
        tasks.append(
            {
                "id": f"t{index}",
                "app": app,
                "operation_id": op_id,
                "args": raw.get("args") if isinstance(raw.get("args"), dict) else {},
                "label": raw.get("label") or (operation.name if operation else f"{app} task"),
                "prompt": raw.get("prompt") or prompt,
            }
        )

    note = str(payload.get("reply") or "").strip()
    missing = [str(m) for m in payload.get("missing") or [] if str(m).strip()]
    if not tasks and missing:
        note = "I need a bit more information: " + "; ".join(missing)
    elif not tasks and not note:
        note = "I could not map that to an action. Try naming the app and what you want done."
    return tasks, note


def _planner_tasks(prompt: str) -> tuple[list[dict[str, Any]], str]:
    llm = build_llm(temperature=0)
    system = PLANNER_PROMPT.format(
        today=datetime.now().strftime("%A %d %B %Y"), tz=config.DEFAULT_TIMEZONE, catalogue=_catalog()
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    reply = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = reply.content if isinstance(reply.content, str) else json.dumps(reply.content, default=str)
    return tasks_from_payload(_extract_json(content), prompt)


def supervisor_node(state: GraphState) -> dict[str, Any]:
    mode = state.get("mode") or "structured"

    if mode == "structured":
        plan = [dict(task) for task in state.get("plan") or []]
        for index, task in enumerate(plan, start=1):
            task.setdefault("id", f"t{index}")
            if not task.get("label"):
                operation = get_operation(task.get("operation_id", ""))
                task["label"] = operation.name if operation else f"{task.get('app')} task"
        return {"tasks": plan}

    prompt = (state.get("prompt") or "").strip()
    if not prompt:
        return {"tasks": [], "answer": "Ask me to do something with Gmail, Calendar, Jira or WhatsApp."}
    try:
        tasks, note = _planner_tasks(prompt)
    except Exception as exc:
        return {
            "tasks": [],
            "answer": f"Planner error: {exc}\n\nAdd an LLM key to .env, or use the **Command Deck** tab "
                      "which executes operations without an LLM.",
        }
    return {"tasks": tasks, "answer": note if not tasks else ""}


def fan_out(state: GraphState) -> list[Send] | str:
    tasks = [task for task in state.get("tasks") or [] if task.get("app") in config.APPS]
    if not tasks:
        return "report"
    return [Send(f"{task['app']}_agent", {"task": task}) for task in tasks]


# --------------------------------------------------------------------------- #
# specialists
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _llm_or_none():
    if not config.llm_configured():
        return None
    try:
        return build_llm()
    except Exception:
        return None


def _make_app_node(app: str) -> Callable[[GraphState], dict[str, Any]]:
    def node(state: GraphState) -> dict[str, Any]:
        task = dict(state.get("task") or {})
        task["app"] = app
        result = execute_task(task, llm=_llm_or_none() if task.get("operation_id") == "auto" else None)
        return {"results": [result]}

    node.__name__ = f"{app}_agent"
    return node


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _line(result: dict[str, Any]) -> str:
    icon = "✅" if result.get("status") == "success" else "⛔"
    app = config.APP_META.get(result.get("app", ""), {})
    detail = result.get("summary") or result.get("error") or ""
    detail = str(detail).replace("\n", " ")[:180]
    return f"{icon} **{app.get('icon', '•')} {app.get('label', result.get('app'))} · {result.get('label', 'task')}** — {detail}"


def report_node(state: GraphState) -> dict[str, Any]:
    results = list(state.get("results") or [])
    planned = state.get("answer") or ""

    if not results:
        return {"answer": planned or "No actions were run."}

    ok = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - ok
    total_ms = sum(int(r.get("ms") or 0) for r in results)
    header = f"**{len(results)} action{'s' if len(results) != 1 else ''} · {ok} succeeded"
    if failed:
        header += f" · {failed} failed"
    header += f" · {total_ms / 1000:.1f}s**"

    body = "\n".join(f"- {_line(r)}" for r in results)
    footnotes = []
    if any((r.get("output") or {}).get("simulated") for r in results):
        footnotes.append("Some apps ran in **SIMULATED** mode — add credentials to `.env` to go live.")
    answer = "\n\n".join(part for part in [header, body, planned, *footnotes] if part)
    return {"answer": answer}


# --------------------------------------------------------------------------- #
# build + run
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_graph():
    graph = StateGraph(GraphState)
    graph.add_node("supervisor", supervisor_node)
    for app in APP_NODES:
        graph.add_node(f"{app}_agent", _make_app_node(app))
    graph.add_node("report", report_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", fan_out, [f"{app}_agent" for app in APP_NODES] + ["report"])
    for app in APP_NODES:
        graph.add_edge(f"{app}_agent", "report")
    graph.add_edge("report", END)
    return graph.compile()


def run_plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute a queued list of structured operations."""
    payload: GraphState = {"mode": "structured", "plan": tasks, "results": [], "answer": ""}
    return get_graph().invoke(payload)


def run_chat(prompt: str) -> dict[str, Any]:
    """Let the supervisor turn natural language into tasks, then execute them."""
    payload: GraphState = {"mode": "chat", "prompt": prompt, "results": [], "answer": ""}
    return get_graph().invoke(payload)


__all__ = ["get_graph", "run_plan", "run_chat", "tool_names"]
