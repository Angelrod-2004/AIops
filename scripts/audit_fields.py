"""Audit: which tool parameters are not surfaced as form fields in the catalog?"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from operations import OPERATIONS  # noqa: E402
from tools.registry import get_tool  # noqa: E402

rows = []
for operation in OPERATIONS:
    tool = get_tool(operation.tool)
    params = tool.args_schema.model_fields
    names = {f.name for f in operation.fields}
    hidden = [name for name in params if name not in names]
    if hidden:
        rows.append((operation.id, hidden))

print(f"{len(rows)} operation(s) with unsurfaced tool params")
for op_id, hidden in rows:
    print(f"  {op_id}: {hidden}")
