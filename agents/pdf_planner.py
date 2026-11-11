"""PDF intake and safe task planning for the Command Deck."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader

from agents.graph import _planner_tasks_from_text, tasks_from_payload

MAX_PDF_BYTES = 25 * 1024 * 1024
# Kept deliberately small: a long PDF planned in one shot produces a plan bigger
# than the model's reply budget, which truncates the JSON mid-object.
MAX_CHUNK_CHARS = 6_000
MAX_PDF_TASKS = 200


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Return selectable text from a PDF, preserving page boundaries."""
    if not data:
        raise ValueError("The uploaded PDF is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("The PDF is larger than 25 MB. Upload a smaller file.")

    try:
        reader = PdfReader(BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:  # pragma: no cover - depends on the file
                raise ValueError(
                    "This PDF is password protected. Remove the password and upload it again."
                ) from exc
        pages = list(reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "That file could not be read as a PDF. It may be corrupt or only renamed to .pdf - "
            "export it again and re-upload."
        ) from exc

    parts: list[str] = []
    for number, page in enumerate(pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            continue
        if text:
            parts.append(f"\n\n--- Page {number} ---\n{text}")
    document = "".join(parts).strip()
    if not document:
        raise ValueError("No selectable text was found. Use an OCR-enabled PDF and upload it again.")
    return document, len(pages)


def _chunks(text: str, size: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split a long document on line boundaries for predictable model context."""
    if len(text) <= size:
        return [text]
    out: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= size:
            out.append(remaining)
            break
        cut = remaining.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    return out


def plan_pdf_tasks(data: bytes, filename: str = "uploaded.pdf") -> dict[str, Any]:
    """Extract a PDF and return reviewed task candidates without executing them."""
    text, page_count = extract_pdf_text(data)
    chunks = _chunks(text)
    tasks: list[dict[str, Any]] = []
    notes: list[str] = []
    failures: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        prompt = (
            f"This is task instructions extracted from {filename}, part {index} of {len(chunks)}. "
            "Create every actionable Gmail, Google Calendar, Jira, and WhatsApp task stated here. "
            "Do not execute anything; return a plan only.\n\n"
            f"{chunk}"
        )
        try:
            payload = _planner_tasks_from_text(prompt)
            chunk_tasks, note = tasks_from_payload(payload, prompt)
        except Exception as exc:
            # One unreadable part must not discard the whole document plan.
            failures.append(f"part {index}/{len(chunks)}: {exc}")
            continue
        if payload.get("recovered"):
            failures.append(
                f"part {index}/{len(chunks)}: model output was cut short; the last planned task may be incomplete"
            )
        for task in chunk_tasks:
            task["source"] = {"filename": filename, "page_count": page_count, "part": index}
            tasks.append(task)
        if note:
            notes.append(note)

    if not tasks:
        detail = (" " + failures[0]) if failures else ""
        raise RuntimeError(
            f"No tasks could be planned from '{filename}'.{detail} "
            "Check that the PDF contains actionable instructions and that the model is reachable."
        )

    if len(tasks) > MAX_PDF_TASKS:
        failures.append(f"kept the first {MAX_PDF_TASKS} of {len(tasks)} planned tasks")
        tasks = tasks[:MAX_PDF_TASKS]

    # Give every task a stable unique id in the combined document plan.
    for index, task in enumerate(tasks, start=1):
        task["id"] = f"pdf-{index}"
    return {
        "tasks": tasks,
        "text_chars": len(text),
        "page_count": page_count,
        "chunks": len(chunks),
        "failed_parts": failures,
        "note": " ".join(dict.fromkeys(notes)),
    }
