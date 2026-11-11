"""Debug helper: print the raw planner reply for a prompt or PDF."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime  # noqa: E402

import config  # noqa: E402
from agents.graph import PLANNER_PROMPT, _catalog, build_llm  # noqa: E402
from agents.pdf_planner import extract_pdf_text  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

target = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "test_plan.pdf")
if target.endswith(".pdf"):
    text, pages = extract_pdf_text(Path(target).read_bytes())
    prompt = (
        f"This is task instructions extracted from {Path(target).name}, part 1 of 1. "
        "Create every actionable Gmail, Google Calendar, Jira, and WhatsApp task stated here. "
        "Do not execute anything; return a plan only.\n\n" + text
    )
else:
    prompt = target

llm = build_llm(temperature=0)
system = PLANNER_PROMPT.format(
    today=datetime.now().strftime("%A %d %B %Y"), tz=config.DEFAULT_TIMEZONE, catalogue=_catalog()
)
reply = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
content = reply.content if isinstance(reply.content, str) else str(reply.content)
print("=" * 30, "RAW REPLY", "=" * 30)
print(content)
print("=" * 72)
print("length:", len(content))
