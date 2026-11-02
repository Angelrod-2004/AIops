"""Static consistency check: operation catalogue <-> tool signatures.

Run:  python scripts/check_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from operations import OPERATIONS  # noqa: E402
from tools.registry import ALL_TOOLS, get_tool  # noqa: E402


def main() -> int:
    problems: list[str] = []
    seen_tools: set[str] = set()

    for op in OPERATIONS:
        tool = get_tool(op.tool)
        if tool is None:
            problems.append(f"{op.id}: tool '{op.tool}' is not registered")
            continue
        seen_tools.add(op.tool)
        fields = tool.args_schema.model_fields
        names = {f.name for f in op.fields}

        unknown = names - set(fields)
        if unknown:
            problems.append(f"{op.id}: fields not accepted by {op.tool}: {sorted(unknown)}")

        missing_required = [name for name, meta in fields.items() if meta.is_required() and name not in names]
        if missing_required:
            problems.append(f"{op.id}: tool requires unexposed params: {missing_required}")

        optional_marked_required = [
            f.name for f in op.fields if f.required and f.name in fields and not fields[f.name].is_required()
        ]
        if optional_marked_required:
            problems.append(f"{op.id}: marked required but tool accepts them as optional: {optional_marked_required}")

    for tool in ALL_TOOLS:
        if tool.name not in seen_tools:
            problems.append(f"tool '{tool.name}' has no catalogue entry")

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"OK · {len(OPERATIONS)} operations · {len(ALL_TOOLS)} tools · signatures aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
