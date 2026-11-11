"""Agent runtime: LLM factory, deterministic tool execution, tool-calling loop."""

from __future__ import annotations

import json
import operator
import time
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

import config
from operations import Operation, get_operation
from tools.registry import get_tool, tools_for

APP_SYSTEM = {
    "gmail": (
        "You are the Gmail specialist on an operations team. You can read, search, send, reply, "
        "label and delete mail. Prefer searching before acting when an id is unknown, and never "
        "invent message ids. Report exactly what you did."
    ),
    "calendar": (
        "You are the Google Calendar specialist. You schedule, reschedule, invite guests, check "
        "availability and manage calendars. Always resolve relative dates against the current "
        "date supplied in the task. Times are ISO-8601."
    ),
    "jira": (
        "You are the Jira specialist. You file and update issues, run workflow transitions, log "
        "work, manage sprints and link issues. Use JQL for searching. Never invent issue keys."
    ),
    "whatsapp": (
        "You are the WhatsApp Cloud API specialist. You send text, media, templates and "
        "interactive messages. Phone numbers are digits with country code and no '+'."
    ),
}


# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #
class GraphState(TypedDict, total=False):
    mode: str  # "structured" | "chat"
    prompt: str
    plan: list[dict[str, Any]]
    task: dict[str, Any]
    tasks: Annotated[list[dict[str, Any]], operator.add]
    results: Annotated[list[dict[str, Any]], operator.add]
    answer: str


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
def build_llm(temperature: float | None = None):
    """Create the chat model for the configured provider."""
    if not config.llm_configured():
        raise RuntimeError(
            f"No LLM key found for provider '{config.LLM_PROVIDER}'. Add one to .env "
            "(OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY) or use the Command Deck, "
            "which runs without an LLM."
        )
    provider = config.LLM_PROVIDER
    model = config.model_name()
    temp = config.LLM_TEMPERATURE if temperature is None else temperature
    max_tokens = config.LLM_MAX_TOKENS

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=temp, max_tokens=max_tokens, timeout=180)
    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("pip install langchain-google-genai to use Gemini") from exc
        return ChatGoogleGenerativeAI(model=model, temperature=temp, max_output_tokens=max_tokens)
    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise RuntimeError("pip install langchain-groq to use Groq") from exc
        return ChatGroq(model=model, temperature=temp, max_tokens=max_tokens, timeout=180)
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError("pip install langchain-ollama to use a local model") from exc
        return ChatOllama(model=model, temperature=temp, num_predict=max_tokens)

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model, "temperature": temp, "timeout": 180, "max_tokens": max_tokens
    }
    if config.OPENAI_API_KEY:
        kwargs["api_key"] = config.OPENAI_API_KEY
    if config.LLM_BASE_URL:
        kwargs["base_url"] = config.LLM_BASE_URL
    return ChatOpenAI(**kwargs)


# --------------------------------------------------------------------------- #
# Tool execution
# --------------------------------------------------------------------------- #
def clean_args(args: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        cleaned[key] = value
    return cleaned


@dataclass
class ToolRun:
    tool: str
    args: dict[str, Any]
    output: str
    ok: bool
    ms: int
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": _redact(self.args), "ok": self.ok, "output": self.output,
                "ms": self.ms, "error": self.error}


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    secret_keys = ("token", "password", "secret", "api_key")
    return {k: ("***" if any(s in k.lower() for s in secret_keys) else v) for k, v in args.items()}


def run_tool(tool_name: str, args: dict[str, Any]) -> ToolRun:
    started = time.perf_counter()
    tool = get_tool(tool_name)
    if tool is None:
        return ToolRun(tool_name, args, json.dumps({"ok": False, "error": f"Unknown tool '{tool_name}'"}),
                       False, 0, f"Unknown tool '{tool_name}'")
    try:
        output = tool.invoke(clean_args(args))
        output = output if isinstance(output, str) else json.dumps(output, indent=2, default=str)
        ok_flag = True
        try:
            ok_flag = bool(json.loads(output).get("ok", True))
        except Exception:
            pass
        elapsed = int((time.perf_counter() - started) * 1000)
        return ToolRun(tool_name, args, output, ok_flag, elapsed)
    except Exception as exc:  # validation errors, missing args, transport errors
        elapsed = int((time.perf_counter() - started) * 1000)
        message = f"{type(exc).__name__}: {exc}"
        return ToolRun(tool_name, args, json.dumps({"ok": False, "error": message}), False, elapsed, message)


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content or "")


def run_agent(app: str, instruction: str, llm=None, max_steps: int | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Tool-calling loop for one app specialist."""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    tools = tools_for(app)
    if not tools:
        return f"No tools registered for '{app}'.", []
    model = (llm or build_llm()).bind_tools(tools)
    messages: list[Any] = [SystemMessage(content=APP_SYSTEM.get(app, "You are a helpful operations agent.")),
                           HumanMessage(content=instruction)]
    steps: list[dict[str, Any]] = []
    limit = max_steps or config.MAX_AGENT_STEPS

    for _ in range(max(1, limit)):
        reply = model.invoke(messages)
        messages.append(reply)
        calls = getattr(reply, "tool_calls", None) or []
        if not calls:
            return _as_text(getattr(reply, "content", "")) or "Done.", steps
        for call in calls:
            outcome = run_tool(call.get("name", ""), call.get("args", {}) or {})
            steps.append(outcome.as_dict())
            messages.append(
                ToolMessage(content=outcome.output, tool_call_id=call.get("id", ""), name=call.get("name", ""))
            )
    return f"Stopped after {limit} steps — the task may need to be split up.", steps


# --------------------------------------------------------------------------- #
# Task execution (shared by every app node)
# --------------------------------------------------------------------------- #
def _first_line(text: str, limit: int = 220) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:limit]


def execute_task(task: dict[str, Any], llm=None) -> dict[str, Any]:
    """Run one queued task: either a catalogued operation or a free-form agent job."""
    started = time.perf_counter()
    app = task.get("app", "")
    operation: Operation | None = get_operation(task.get("operation_id", ""))
    label = task.get("label") or (operation.name if operation else "Agent task")
    base = {
        "id": task.get("id") or f"{app}-{int(started * 1000)}",
        "app": app,
        "label": label,
        "operation_id": task.get("operation_id", ""),
        "instruction": task.get("prompt", ""),
        "args": _redact(clean_args(task.get("args"))),
        "steps": [],
        "started_at": time.strftime("%H:%M:%S"),
    }

    # Defence in depth: a review-gated task must never reach a tool, even if a
    # caller bypasses the Streamlit queue controls.
    if task.get("approval_required") and not task.get("approved"):
        return {
            **base,
            "status": "blocked",
            "ms": 0,
            "error": "Human approval is required before this task can execute.",
            "output": {"ok": False, "blocked": True, "error": "Human approval required"},
        }

    # Free-form job -> the app's agent decides which tools to call.
    if operation is None or task.get("operation_id") == "auto":
        if not config.llm_configured():
            return {**base, "status": "error", "ms": 0,
                    "error": "Free-form agent tasks need an LLM key in .env.",
                    "output": {"ok": False, "error": "LLM not configured"}}
        try:
            instruction = task.get("prompt") or task.get("instruction") or ""
            if task.get("args"):
                instruction += f"\n\nProvided values: {json.dumps(clean_args(task.get('args')), ensure_ascii=False)}"
            text, steps = run_agent(app, instruction, llm=llm)
            elapsed = int((time.perf_counter() - started) * 1000)
            return {**base, "steps": steps, "status": "success" if steps else "error", "ms": elapsed,
                    "output": {"ok": bool(steps), "answer": text}, "summary": _first_line(text)}
        except Exception as exc:
            return {**base, "status": "error", "ms": int((time.perf_counter() - started) * 1000),
                    "error": str(exc), "output": {"ok": False, "error": str(exc)}}

    # Catalogued operation -> deterministic single tool call.
    args = clean_args(task.get("args"))
    missing = [f.label for f in operation.required_fields if not str(args.get(f.name, "")).strip()]
    if missing:
        return {**base, "status": "error", "ms": 0, "error": f"Missing required field(s): {', '.join(missing)}",
                "output": {"ok": False, "error": f"Missing required field(s): {', '.join(missing)}"}}

    outcome = run_tool(operation.tool, args)
    try:
        parsed = json.loads(outcome.output)
    except Exception:
        parsed = {"ok": outcome.ok, "raw": outcome.output}
    elapsed = int((time.perf_counter() - started) * 1000)
    summary = _summarise_payload(parsed)
    return {
        **base,
        "status": "success" if outcome.ok else "error",
        "ms": elapsed,
        "steps": [outcome.as_dict()],
        "output": parsed,
        "error": "" if outcome.ok else outcome.error or str(parsed.get("error", "")),
        "summary": summary,
    }


def _summarise_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:200]
    if payload.get("simulated"):
        return "Simulated (no credentials) - add keys in .env to go live."
    preferred = ("key", "message_id", "event", "id", "count", "summary", "url", "answer", "total", "saved_to")
    bits = []
    for key in preferred:
        if key in payload and payload[key] not in (None, "", [], {}):
            value = payload[key]
            if isinstance(value, dict):
                value = value.get("summary") or value.get("id") or value
            bits.append(f"{key}={str(value)[:80]}")
        if len(bits) >= 3:
            break
    if not bits and payload.get("error"):
        return str(payload["error"])[:200]
    return " · ".join(bits) or "Completed."
