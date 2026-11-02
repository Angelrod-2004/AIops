"""Tool registry - one place that knows every tool, grouped by app."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import BaseTool

from .calendar_tools import CALENDAR_TOOLS
from .gmail_tools import GMAIL_TOOLS
from .jira_tools import JIRA_TOOLS
from .whatsapp_tools import WHATSAPP_TOOLS

APP_TOOLS: dict[str, list[BaseTool]] = {
    "gmail": GMAIL_TOOLS,
    "calendar": CALENDAR_TOOLS,
    "jira": JIRA_TOOLS,
    "whatsapp": WHATSAPP_TOOLS,
}

ALL_TOOLS: list[BaseTool] = [tool for tools in APP_TOOLS.values() for tool in tools]
TOOL_INDEX: dict[str, BaseTool] = {tool.name: tool for tool in ALL_TOOLS}


def tools_for(app: str) -> list[BaseTool]:
    return APP_TOOLS.get(app, [])


def get_tool(name: str) -> BaseTool | None:
    return TOOL_INDEX.get(name)


def tool_callable(name: str) -> Callable | None:
    tool = TOOL_INDEX.get(name)
    return getattr(tool, "func", None) if tool else None


def tool_names() -> list[str]:
    return sorted(TOOL_INDEX)
