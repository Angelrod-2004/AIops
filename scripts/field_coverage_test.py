"""Field-coverage test: every catalog field must render a widget in the UI.

Boots app.py in Streamlit's AppTest, walks all four apps and every operation,
and asserts that each declared field produced at least one widget keyed
`<operation_id>__<field_name>`. This is the regression guard for fields that
silently vanish from the form.

Run:  python scripts/field_coverage_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from streamlit.testing.v1 import AppTest  # noqa: E402

from operations import OPS_BY_APP  # noqa: E402

WIDGET_ATTRS = (
    "text_input", "text_area", "number_input", "selectbox", "toggle", "multiselect",
    "date_input", "time_input", "file_uploader", "color_picker", "slider",
)


def widget_keys(at: AppTest) -> set[str]:
    keys: set[str] = set()
    for attr in WIDGET_ATTRS:
        try:
            elements = getattr(at, attr)
        except Exception:
            continue
        for element in elements:
            key = getattr(element, "key", None)
            if key:
                keys.add(str(key))
    return keys


def main() -> int:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.run()
    if at.exception:
        for exc in at.exception:
            print(exc.stack_trace)
        return 1

    problems: list[str] = []
    checked_ops = 0
    checked_fields = 0

    for app, operations in OPS_BY_APP.items():
        pick = next((b for b in at.button if b.key == f"pick_{app}"), None)
        if pick is None:
            problems.append(f"{app}: app selector button missing")
            continue
        pick.click().run()
        if at.exception:
            problems.append(f"{app}: exception switching app -> {at.exception}")
            continue

        for operation in operations:
            selector = next((s for s in at.selectbox if s.key == f"op_{app}"), None)
            if selector is None:
                problems.append(f"{app}: operation selectbox missing")
                break
            name = next((o.name for o in operations if o.id == operation.id), None)
            if name is None:
                continue
            selector.select(name).run()
            if at.exception:
                problems.append(f"{operation.id}: exception while rendering form -> {at.exception}")
                continue

            checked_ops += 1
            keys = widget_keys(at)
            for field in operation.fields:
                checked_fields += 1
                base = f"{operation.id}__{field.name}"
                rendered = any(k == base or k.startswith(f"{base}__") for k in keys)
                if not rendered:
                    problems.append(f"{operation.id}: field '{field.name}' ({field.kind}) rendered no widget")

    print(f"checked {checked_ops} operations · {checked_fields} fields")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("every catalog field rendered a widget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
