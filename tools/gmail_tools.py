"""Gmail tools - full mailbox operations against the Gmail v1 REST API."""

from __future__ import annotations

import base64
import re
from email import policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

import config
from ._utils import b64url, err, gmail_service, mime_for, ok, save_bytes, simulated, split_csv

APP = "gmail"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _strip_tags(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
    return re.sub(r"<[^>]+>", "", text).strip() or "This message contains HTML content."


def _build_raw(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html: bool = False,
    attachments: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> str:
    msg = EmailMessage(policy=policy.SMTP)
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject or "(no subject)"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    if html:
        msg.set_content(_strip_tags(body))
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body or "")
    for path in split_csv(attachments):
        file_path = Path(path).expanduser()
        if not file_path.exists():
            raise FileNotFoundError(f"attachment not found: {file_path}")
        maintype, _, subtype = mime_for(str(file_path)).partition("/")
        msg.add_attachment(file_path.read_bytes(), maintype=maintype, subtype=subtype, filename=file_path.name)
    return b64url(msg.as_bytes())


def _summary(message: dict[str, Any]) -> dict[str, Any]:
    headers = {h.get("name", "").lower(): h.get("value", "") for h in message.get("payload", {}).get("headers", [])}
    labels = message.get("labelIds", [])
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "(no subject)"),
        "date": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
        "labels": labels,
        "unread": "UNREAD" in labels,
    }


def _collect_body(part: dict[str, Any], texts: list[str], attachments: list[dict[str, Any]]) -> None:
    mime = part.get("mimeType", "")
    body = part.get("body", {}) or {}
    if part.get("filename"):
        attachments.append(
            {
                "filename": part.get("filename"),
                "mime": mime,
                "attachment_id": body.get("attachmentId"),
                "size": body.get("size", 0),
            }
        )
    data = body.get("data")
    if data and mime in ("text/plain", "text/html"):
        try:
            texts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
        except Exception:
            pass
    for child in part.get("parts", []) or []:
        _collect_body(child, texts, attachments)


def _read(message_id: str) -> dict[str, Any]:
    raw = gmail_service().users().messages().get(userId="me", id=message_id, format="full").execute()
    texts: list[str] = []
    attachments: list[dict[str, Any]] = []
    _collect_body(raw.get("payload", {}), texts, attachments)
    return {**_summary(raw), "body": ("\n".join(texts)).strip()[:20000], "attachments": attachments}


def _modify(message_id: str, add: list[str], remove: list[str]) -> dict[str, Any]:
    return (
        gmail_service()
        .users()
        .messages()
        .modify(userId="me", id=message_id, body={"addLabelIds": add, "removeLabelIds": remove})
        .execute()
    )


# --------------------------------------------------------------------------- #
# send / reply / forward
# --------------------------------------------------------------------------- #
@tool
def gmail_send_message(
    to: str, subject: str, body: str, cc: str = "", bcc: str = "", html: bool = False, attachments: str = ""
) -> str:
    """Send a new email. `to`/`cc`/`bcc` are comma separated; `attachments` is a comma separated list of local file paths. Set html=True to send `body` as HTML."""
    if config.simulating(APP):
        return simulated(
            APP, "send_message", to=to, subject=subject, cc=cc, attachments=split_csv(attachments),
            message_id="sim-msg-1", thread_id="sim-thread-1",
        )
    try:
        raw = _build_raw(to, subject, body, cc, bcc, html, attachments)
        sent = gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
        return ok(message_id=sent.get("id"), thread_id=sent.get("threadId"), to=to, subject=subject)
    except Exception as exc:
        return err(f"send_message failed: {exc}")


@tool
def gmail_reply_message(message_id: str, body: str, html: bool = False, reply_all: bool = False) -> str:
    """Reply to an existing message, keeping it in the same thread. reply_all=True also replies to every recipient."""
    if config.simulating(APP):
        return simulated(APP, "reply_message", to_message=message_id, body=body[:120], reply_all=reply_all)
    try:
        original = gmail_service().users().messages().get(userId="me", id=message_id, format="metadata",
                                                         metadataHeaders=["From", "To", "Cc", "Subject", "Message-ID"]).execute()
        headers = {h["name"].lower(): h["value"] for h in original.get("payload", {}).get("headers", [])}
        sender = headers.get("from", "")
        me = gmail_service().users().getProfile(userId="me").execute().get("emailAddress", "")
        subject = headers.get("subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        cc = ""
        if reply_all:
            cc = ", ".join([a for a in [headers.get("to", ""), headers.get("cc", "")] if a and me not in a])
        raw = _build_raw(
            to=sender, subject=subject, body=body, cc=cc, html=html,
            in_reply_to=headers.get("message-id", ""), references=headers.get("message-id", ""),
        )
        sent = (
            gmail_service()
            .users()
            .messages()
            .send(userId="me", body={"raw": raw, "threadId": original.get("threadId")})
            .execute()
        )
        return ok(message_id=sent.get("id"), thread_id=sent.get("threadId"), to=sender, subject=subject)
    except Exception as exc:
        return err(f"reply_message failed: {exc}")


@tool
def gmail_forward_message(message_id: str, to: str, note: str = "", include_attachments: bool = True) -> str:
    """Forward a message (with optional note and the original attachments) to `to`."""
    if config.simulating(APP):
        return simulated(APP, "forward_message", message_id=message_id, to=to, note=note[:120])
    try:
        original = _read(message_id)
        service = gmail_service()
        msg = EmailMessage(policy=policy.SMTP)
        msg["To"] = to
        msg["Subject"] = original["subject"] if original["subject"].lower().startswith("fwd") else f"Fwd: {original['subject']}"
        prefix = f"{note}\n\n" if note else ""
        msg.set_content(f"{prefix}---------- Forwarded message ----------\nFrom: {original['from']}\n"
                        f"Date: {original['date']}\nSubject: {original['subject']}\n\n{original['body']}")
        if include_attachments:
            for att in original["attachments"]:
                if not att.get("attachment_id"):
                    continue
                data = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=att["attachment_id"]
                ).execute()
                maintype, _, subtype = (att.get("mime") or "application/octet-stream").partition("/")
                msg.add_attachment(base64.urlsafe_b64decode(data["data"]), maintype=maintype,
                                   subtype=subtype, filename=att.get("filename") or "attachment")
        sent = service.users().messages().send(userId="me", body={"raw": b64url(msg.as_bytes())}).execute()
        return ok(message_id=sent.get("id"), thread_id=sent.get("threadId"), to=to, attachments=len(original["attachments"]))
    except Exception as exc:
        return err(f"forward_message failed: {exc}")


# --------------------------------------------------------------------------- #
# read / search
# --------------------------------------------------------------------------- #
@tool
def gmail_list_messages(query: str = "", label: str = "", max_results: int = 10) -> str:
    """List the most recent messages. `query` uses Gmail search syntax (e.g. 'from:boss is:unread newer_than:2d'), `label` filters by label id/name."""
    if config.simulating(APP):
        return simulated(APP, "list_messages", query=query, label=label, messages=[
            {"id": "sim-1", "from": "ada@example.com", "subject": "Q4 planning", "snippet": "Attaching the deck…", "unread": True},
            {"id": "sim-2", "from": "ops@example.com", "subject": "Deploy finished", "snippet": "All green.", "unread": False},
        ])
    try:
        service = gmail_service()
        response = service.users().messages().list(
            userId="me", q=query or None, maxResults=max(1, min(int(max_results), 100)),
            labelIds=split_csv(label) or None,
        ).execute()
        found = []
        for stub in response.get("messages", [])[: int(max_results)]:
            detail = service.users().messages().get(
                userId="me", id=stub["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()
            found.append(_summary(detail))
        return ok(count=len(found), messages=found)
    except Exception as exc:
        return err(f"list_messages failed: {exc}")


@tool
def gmail_search_messages(query: str, max_results: int = 10) -> str:
    """Search the mailbox with Gmail query syntax, e.g. 'has:attachment from:finance after:2026/01/01'."""
    return gmail_list_messages.invoke({"query": query, "max_results": max_results})


@tool
def gmail_read_message(message_id: str) -> str:
    """Read one message in full: headers, plain-text body and attachment list."""
    if config.simulating(APP):
        return simulated(APP, "read_message", id=message_id, subject="Q4 planning",
                         **{"from": "ada@example.com", "body": "Hi! Attaching the deck for review.", "attachments": []})
    try:
        return ok(message=_read(message_id))
    except Exception as exc:
        return err(f"read_message failed: {exc}")


@tool
def gmail_get_profile() -> str:
    """Return the signed-in mailbox address, total message count and thread count."""
    if config.simulating(APP):
        return simulated(APP, "get_profile", emailAddress="you@example.com", messagesTotal=1284, threadsTotal=902)
    try:
        return ok(profile=gmail_service().users().getProfile(userId="me").execute())
    except Exception as exc:
        return err(f"get_profile failed: {exc}")


# --------------------------------------------------------------------------- #
# drafts
# --------------------------------------------------------------------------- #
@tool
def gmail_create_draft(
    to: str, subject: str, body: str, cc: str = "", bcc: str = "", html: bool = False, attachments: str = ""
) -> str:
    """Create (but do not send) a draft email. Attachments are local file paths, comma separated."""
    if config.simulating(APP):
        return simulated(APP, "create_draft", to=to, subject=subject, draft_id="sim-draft-1")
    try:
        raw = _build_raw(to, subject, body, cc, bcc, html, attachments)
        draft = gmail_service().users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        return ok(draft_id=draft.get("id"), message=draft.get("message", {}).get("id"), to=to, subject=subject)
    except Exception as exc:
        return err(f"create_draft failed: {exc}")


@tool
def gmail_list_drafts(max_results: int = 10) -> str:
    """List saved drafts."""
    if config.simulating(APP):
        return simulated(APP, "list_drafts", drafts=[{"id": "sim-draft-1", "subject": "Draft: launch notes"}])
    try:
        service = gmail_service()
        response = service.users().drafts().list(userId="me", maxResults=max(1, min(int(max_results), 50))).execute()
        drafts = []
        for stub in response.get("drafts", []):
            detail = service.users().drafts().get(userId="me", id=stub["id"], format="metadata").execute()
            item = _summary(detail.get("message", {}))
            drafts.append({"draft_id": stub["id"], **item})
        return ok(count=len(drafts), drafts=drafts)
    except Exception as exc:
        return err(f"list_drafts failed: {exc}")


@tool
def gmail_send_draft(draft_id: str) -> str:
    """Send a previously created draft."""
    if config.simulating(APP):
        return simulated(APP, "send_draft", draft_id=draft_id, message_id="sim-msg-2")
    try:
        sent = gmail_service().users().drafts().send(userId="me", body={"id": draft_id}).execute()
        return ok(message_id=sent.get("id"), thread_id=sent.get("threadId"), draft_id=draft_id)
    except Exception as exc:
        return err(f"send_draft failed: {exc}")


@tool
def gmail_delete_draft(draft_id: str) -> str:
    """Permanently delete a draft."""
    if config.simulating(APP):
        return simulated(APP, "delete_draft", draft_id=draft_id)
    try:
        gmail_service().users().drafts().delete(userId="me", id=draft_id).execute()
        return ok(deleted_draft=draft_id)
    except Exception as exc:
        return err(f"delete_draft failed: {exc}")


# --------------------------------------------------------------------------- #
# lifecycle / labels
# --------------------------------------------------------------------------- #
@tool
def gmail_trash_message(message_id: str) -> str:
    """Move a message to Trash (recoverable)."""
    if config.simulating(APP):
        return simulated(APP, "trash_message", id=message_id)
    try:
        return ok(trashed=gmail_service().users().messages().trash(userId="me", id=message_id).execute().get("id"))
    except Exception as exc:
        return err(f"trash_message failed: {exc}")


@tool
def gmail_untrash_message(message_id: str) -> str:
    """Restore a message from Trash."""
    if config.simulating(APP):
        return simulated(APP, "untrash_message", id=message_id)
    try:
        return ok(restored=gmail_service().users().messages().untrash(userId="me", id=message_id).execute().get("id"))
    except Exception as exc:
        return err(f"untrash_message failed: {exc}")


@tool
def gmail_delete_message(message_id: str) -> str:
    """Permanently delete a message (bypasses Trash). Irreversible."""
    if config.simulating(APP):
        return simulated(APP, "delete_message", id=message_id)
    try:
        gmail_service().users().messages().delete(userId="me", id=message_id).execute()
        return ok(deleted=message_id)
    except Exception as exc:
        return err(f"delete_message failed: {exc}")


@tool
def gmail_modify_labels(message_id: str, add: str = "", remove: str = "") -> str:
    """Add and/or remove labels on a message. Pass label ids or well-known ids like INBOX, UNREAD, STARRED, IMPORTANT, SPAM, TRASH."""
    if config.simulating(APP):
        return simulated(APP, "modify_labels", id=message_id, added=split_csv(add), removed=split_csv(remove))
    try:
        result = _modify(message_id, split_csv(add), split_csv(remove))
        return ok(id=result.get("id"), labels=result.get("labelIds", []))
    except Exception as exc:
        return err(f"modify_labels failed: {exc}")


@tool
def gmail_mark_read(message_id: str) -> str:
    """Mark a message as read."""
    if config.simulating(APP):
        return simulated(APP, "mark_read", id=message_id)
    try:
        _modify(message_id, [], ["UNREAD"])
        return ok(id=message_id, read=True)
    except Exception as exc:
        return err(f"mark_read failed: {exc}")


@tool
def gmail_mark_unread(message_id: str) -> str:
    """Mark a message as unread."""
    if config.simulating(APP):
        return simulated(APP, "mark_unread", id=message_id)
    try:
        _modify(message_id, ["UNREAD"], [])
        return ok(id=message_id, read=False)
    except Exception as exc:
        return err(f"mark_unread failed: {exc}")


@tool
def gmail_list_labels() -> str:
    """List every label in the mailbox with its id, type and message counts."""
    if config.simulating(APP):
        return simulated(APP, "list_labels", labels=[
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "Label_1", "name": "Clients", "type": "user", "messagesTotal": 42},
        ])
    try:
        labels = gmail_service().users().labels().list(userId="me").execute().get("labels", [])
        return ok(count=len(labels), labels=labels)
    except Exception as exc:
        return err(f"list_labels failed: {exc}")


@tool
def gmail_create_label(name: str) -> str:
    """Create a new user label."""
    if config.simulating(APP):
        return simulated(APP, "create_label", name=name, id="Label_sim")
    try:
        label = gmail_service().users().labels().create(
            userId="me", body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        ).execute()
        return ok(id=label.get("id"), name=label.get("name"))
    except Exception as exc:
        return err(f"create_label failed: {exc}")


@tool
def gmail_delete_label(label_id: str) -> str:
    """Delete a user label."""
    if config.simulating(APP):
        return simulated(APP, "delete_label", id=label_id)
    try:
        gmail_service().users().labels().delete(userId="me", id=label_id).execute()
        return ok(deleted_label=label_id)
    except Exception as exc:
        return err(f"delete_label failed: {exc}")


# --------------------------------------------------------------------------- #
# threads + attachments
# --------------------------------------------------------------------------- #
@tool
def gmail_list_threads(query: str = "", max_results: int = 10) -> str:
    """List conversation threads (optionally filtered by a Gmail query)."""
    if config.simulating(APP):
        return simulated(APP, "list_threads", threads=[{"id": "sim-thread-1", "snippet": "Q4 planning", "messages": 3}])
    try:
        service = gmail_service()
        response = service.users().threads().list(
            userId="me", q=query or None, maxResults=max(1, min(int(max_results), 50))
        ).execute()
        threads = []
        for stub in response.get("threads", []):
            detail = service.users().threads().get(userId="me", id=stub["id"], format="metadata").execute()
            threads.append(
                {
                    "thread_id": stub["id"],
                    "snippet": detail.get("snippet", ""),
                    "messages": len(detail.get("messages", [])),
                    "subjects": [h.get("value") for m in detail.get("messages", [])
                                 for h in m.get("payload", {}).get("headers", []) if h.get("name") == "Subject"][:1],
                }
            )
        return ok(count=len(threads), threads=threads)
    except Exception as exc:
        return err(f"list_threads failed: {exc}")


@tool
def gmail_get_thread(thread_id: str) -> str:
    """Read a whole conversation thread."""
    if config.simulating(APP):
        return simulated(APP, "get_thread", thread_id=thread_id, messages=[{"id": "sim-1", "subject": "Q4 planning"}])
    try:
        detail = gmail_service().users().threads().get(userId="me", id=thread_id, format="metadata").execute()
        return ok(thread_id=thread_id, messages=[_summary(m) for m in detail.get("messages", [])])
    except Exception as exc:
        return err(f"get_thread failed: {exc}")


@tool
def gmail_trash_thread(thread_id: str) -> str:
    """Move an entire thread to Trash."""
    if config.simulating(APP):
        return simulated(APP, "trash_thread", thread_id=thread_id)
    try:
        gmail_service().users().threads().trash(userId="me", id=thread_id).execute()
        return ok(trashed_thread=thread_id)
    except Exception as exc:
        return err(f"trash_thread failed: {exc}")


@tool
def gmail_delete_thread(thread_id: str) -> str:
    """Permanently delete an entire thread. Irreversible."""
    if config.simulating(APP):
        return simulated(APP, "delete_thread", thread_id=thread_id)
    try:
        gmail_service().users().threads().delete(userId="me", id=thread_id).execute()
        return ok(deleted_thread=thread_id)
    except Exception as exc:
        return err(f"delete_thread failed: {exc}")


@tool
def gmail_download_attachment(message_id: str, attachment_id: str, save_path: str) -> str:
    """Download one attachment to a local file path."""
    if config.simulating(APP):
        return simulated(APP, "download_attachment", message_id=message_id, attachment_id=attachment_id, saved_to=save_path)
    try:
        data = gmail_service().users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        target = save_bytes(save_path, base64.urlsafe_b64decode(data["data"]))
        return ok(saved_to=target, bytes=len(base64.urlsafe_b64decode(data["data"])))
    except Exception as exc:
        return err(f"download_attachment failed: {exc}")


GMAIL_TOOLS = [
    gmail_send_message,
    gmail_reply_message,
    gmail_forward_message,
    gmail_list_messages,
    gmail_search_messages,
    gmail_read_message,
    gmail_get_profile,
    gmail_create_draft,
    gmail_list_drafts,
    gmail_send_draft,
    gmail_delete_draft,
    gmail_trash_message,
    gmail_untrash_message,
    gmail_delete_message,
    gmail_modify_labels,
    gmail_mark_read,
    gmail_mark_unread,
    gmail_list_labels,
    gmail_create_label,
    gmail_delete_label,
    gmail_list_threads,
    gmail_get_thread,
    gmail_trash_thread,
    gmail_delete_thread,
    gmail_download_attachment,
]
