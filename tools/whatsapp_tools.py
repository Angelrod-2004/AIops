"""WhatsApp Cloud API tools - text, media, templates, interactive messages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

import config
from ._utils import (
    err,
    mime_for,
    ok,
    parse_json_arg,
    save_bytes,
    simulated,
    wa_media_payload,
    wa_request,
)

APP = "whatsapp"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _to(number: str) -> str:
    digits = re.sub(r"[^\d]", "", str(number or ""))
    if not digits:
        raise ValueError("recipient phone number is required (digits with country code)")
    return digits


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("messaging_product", "whatsapp")
    return wa_request("POST", f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages", json=payload)


def _message_id(response: dict[str, Any]) -> str:
    messages = response.get("messages") or [{}]
    return messages[0].get("id", "")


def _reply_buttons(raw: Any) -> list[dict[str, Any]]:
    items = parse_json_arg(raw, "buttons") or []
    if not isinstance(items, list) or not items:
        raise ValueError('buttons must be a JSON array like [{"id":"yes","title":"Yes"}]')
    if len(items) > 3:
        raise ValueError("WhatsApp allows at most 3 reply buttons")
    out = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            item = {"id": f"btn_{index}", "title": item}
        title = str(item.get("title", "")).strip()[:20]
        if not title:
            raise ValueError("each button needs a title")
        out.append({"type": "reply", "reply": {"id": str(item.get("id") or f"btn_{index}"), "title": title}})
    return out


def _list_sections(raw: Any) -> list[dict[str, Any]]:
    sections = parse_json_arg(raw, "sections") or []
    if not isinstance(sections, list) or not sections:
        raise ValueError('sections must be a JSON array like [{"title":"Slots","rows":[{"id":"1","title":"9am"}]}]')
    rows = sum(len(s.get("rows", [])) for s in sections)
    if rows > 10:
        raise ValueError("WhatsApp allows at most 10 total rows across all list sections")
    return sections


# --------------------------------------------------------------------------- #
# text / templates
# --------------------------------------------------------------------------- #
@tool
def wa_send_text(to: str, body: str, preview_url: bool = False) -> str:
    """Send a plain text WhatsApp message. `to` is the recipient's phone number with country code (digits only, e.g. 919876543210)."""
    if config.simulating(APP):
        return simulated(APP, "send_text", to=to, body=body[:160], message_id="wamid.sim-text")
    try:
        response = _send({"to": _to(to), "type": "text", "text": {"body": body, "preview_url": bool(preview_url)}})
        return ok(message_id=_message_id(response), to=_to(to), type="text")
    except Exception as exc:
        return err(f"send_text failed: {exc}")


@tool
def wa_send_template(to: str, template_name: str, language_code: str = "en_US", components_json: str = "") -> str:
    """Send a pre-approved template message (required for the first contact outside the 24h window). `components_json` feeds template variables."""
    if config.simulating(APP):
        return simulated(APP, "send_template", to=to, template=template_name, language=language_code)
    try:
        template: dict[str, Any] = {"name": template_name, "language": {"code": language_code or "en_US"}}
        components = parse_json_arg(components_json, "components_json")
        if components:
            template["components"] = components
        response = _send({"to": _to(to), "type": "template", "template": template})
        return ok(message_id=_message_id(response), to=_to(to), template=template_name)
    except Exception as exc:
        return err(f"send_template failed: {exc}")


# --------------------------------------------------------------------------- #
# media
# --------------------------------------------------------------------------- #
@tool
def wa_send_image(to: str, image_url: str, caption: str = "") -> str:
    """Send an image from a public URL or an existing media id."""
    if config.simulating(APP):
        return simulated(APP, "send_image", to=to, image=image_url, caption=caption[:80])
    try:
        payload = wa_media_payload(image_url, "image", caption)
        payload["to"] = _to(to)
        response = _send(payload)
        return ok(message_id=_message_id(response), type="image")
    except Exception as exc:
        return err(f"send_image failed: {exc}")


@tool
def wa_send_document(to: str, document_url: str, caption: str = "", filename: str = "") -> str:
    """Send a document (PDF, invoice, sheet…) from a public URL or media id."""
    if config.simulating(APP):
        return simulated(APP, "send_document", to=to, document=document_url, filename=filename)
    try:
        payload = wa_media_payload(document_url, "document", caption, filename)
        payload["to"] = _to(to)
        response = _send(payload)
        return ok(message_id=_message_id(response), type="document")
    except Exception as exc:
        return err(f"send_document failed: {exc}")


@tool
def wa_send_audio(to: str, audio_url: str) -> str:
    """Send an audio clip (aac/amr/mp3/m4a/ogg, <=16MB) from a public URL or media id."""
    if config.simulating(APP):
        return simulated(APP, "send_audio", to=to, audio=audio_url)
    try:
        payload = wa_media_payload(audio_url, "audio")
        payload["to"] = _to(to)
        response = _send(payload)
        return ok(message_id=_message_id(response), type="audio")
    except Exception as exc:
        return err(f"send_audio failed: {exc}")


@tool
def wa_send_video(to: str, video_url: str, caption: str = "") -> str:
    """Send a video from a public URL or media id."""
    if config.simulating(APP):
        return simulated(APP, "send_video", to=to, video=video_url, caption=caption[:80])
    try:
        payload = wa_media_payload(video_url, "video", caption)
        payload["to"] = _to(to)
        response = _send(payload)
        return ok(message_id=_message_id(response), type="video")
    except Exception as exc:
        return err(f"send_video failed: {exc}")


@tool
def wa_send_sticker(to: str, sticker_url: str) -> str:
    """Send a WEBP sticker from a public URL or media id."""
    if config.simulating(APP):
        return simulated(APP, "send_sticker", to=to, sticker=sticker_url)
    try:
        payload = wa_media_payload(sticker_url, "sticker")
        payload["to"] = _to(to)
        response = _send(payload)
        return ok(message_id=_message_id(response), type="sticker")
    except Exception as exc:
        return err(f"send_sticker failed: {exc}")


# --------------------------------------------------------------------------- #
# rich / interactive
# --------------------------------------------------------------------------- #
@tool
def wa_send_location(to: str, latitude: float, longitude: float, name: str = "", address: str = "") -> str:
    """Share a location pin."""
    if config.simulating(APP):
        return simulated(APP, "send_location", to=to, latitude=latitude, longitude=longitude)
    try:
        response = _send({
            "to": _to(to),
            "type": "location",
            "location": {"latitude": float(latitude), "longitude": float(longitude), "name": name, "address": address},
        })
        return ok(message_id=_message_id(response), type="location")
    except Exception as exc:
        return err(f"send_location failed: {exc}")


@tool
def wa_send_contact_card(to: str, contact_json: str) -> str:
    """Send a contact card. `contact_json` is a JSON array, e.g. [{"name":{"formatted":"Ada Lovelace","first_name":"Ada"},"phones":[{"phone":"+919876543210","type":"CELL"}]}]."""
    if config.simulating(APP):
        return simulated(APP, "send_contact", to=to)
    try:
        contacts = parse_json_arg(contact_json, "contact_json")
        if not isinstance(contacts, list):
            raise ValueError("contact_json must be a JSON array")
        response = _send({"to": _to(to), "type": "contacts", "contacts": contacts})
        return ok(message_id=_message_id(response), type="contacts", count=len(contacts))
    except Exception as exc:
        return err(f"send_contact_card failed: {exc}")


@tool
def wa_send_buttons(to: str, body_text: str, buttons_json: str, header_text: str = "", footer_text: str = "") -> str:
    """Send up to 3 tappable reply buttons. `buttons_json` e.g. [{"id":"yes","title":"Approve"},{"id":"no","title":"Reject"}] (titles <= 20 chars)."""
    if config.simulating(APP):
        return simulated(APP, "send_buttons", to=to, body=body_text[:80])
    try:
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body_text[:1024]},
            "action": {"buttons": _reply_buttons(buttons_json)},
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}
        response = _send({"to": _to(to), "type": "interactive", "interactive": interactive})
        return ok(message_id=_message_id(response), type="interactive/buttons")
    except Exception as exc:
        return err(f"send_buttons failed: {exc}")


@tool
def wa_send_list(to: str, body_text: str, button_text: str, sections_json: str, header_text: str = "", footer_text: str = "") -> str:
    """Send a list picker (max 10 rows). `sections_json` e.g. [{"title":"Slots","rows":[{"id":"9am","title":"9:00 AM","description":"Free"}]}]."""
    if config.simulating(APP):
        return simulated(APP, "send_list", to=to, body=body_text[:80])
    try:
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body_text[:1024]},
            "action": {"button": button_text[:20], "sections": _list_sections(sections_json)},
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}
        response = _send({"to": _to(to), "type": "interactive", "interactive": interactive})
        return ok(message_id=_message_id(response), type="interactive/list")
    except Exception as exc:
        return err(f"send_list failed: {exc}")


@tool
def wa_send_cta_button(to: str, body_text: str, button_text: str, url: str, header_text: str = "", footer_text: str = "") -> str:
    """Send a message with a single call-to-action URL button."""
    if config.simulating(APP):
        return simulated(APP, "send_cta", to=to, url=url)
    try:
        interactive: dict[str, Any] = {
            "type": "cta_url",
            "body": {"text": body_text[:1024]},
            "action": {"name": "cta_url", "parameters": {"display_text": button_text[:20], "url": url}},
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive["footer"] = {"text": footer_text[:60]}
        response = _send({"to": _to(to), "type": "interactive", "interactive": interactive})
        return ok(message_id=_message_id(response), type="interactive/cta_url")
    except Exception as exc:
        return err(f"send_cta_button failed: {exc}")


@tool
def wa_send_reaction(to: str, message_id: str, emoji: str = "👍") -> str:
    """React to a message with an emoji."""
    if config.simulating(APP):
        return simulated(APP, "send_reaction", to=to, message_id=message_id, emoji=emoji)
    try:
        response = _send({"to": _to(to), "type": "reaction", "reaction": {"message_id": message_id, "emoji": emoji}})
        return ok(message_id=_message_id(response), type="reaction")
    except Exception as exc:
        return err(f"send_reaction failed: {exc}")


@tool
def wa_mark_read(message_id: str) -> str:
    """Mark an inbound message as read (blue ticks)."""
    if config.simulating(APP):
        return simulated(APP, "mark_read", message_id=message_id)
    try:
        response = wa_request("POST", f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
                              json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id})
        return ok(success=response.get("success", True), message_id=message_id)
    except Exception as exc:
        return err(f"mark_read failed: {exc}")


# --------------------------------------------------------------------------- #
# media + account management
# --------------------------------------------------------------------------- #
@tool
def wa_get_media(media_id: str, save_path: str = "") -> str:
    """Resolve a media id to a temporary download URL and optionally save the file locally."""
    if config.simulating(APP):
        return simulated(APP, "get_media", media_id=media_id, saved_to=save_path or "downloads/media.bin")
    try:
        import requests

        info = wa_request("GET", media_id)
        url = info.get("url", "")
        saved = ""
        if save_path and url:
            raw = requests.get(url, headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}, timeout=120)
            raw.raise_for_status()
            saved = save_bytes(save_path, raw.content)
        return ok(media_id=media_id, url=url, mime_type=info.get("mimeType"), saved_to=saved)
    except Exception as exc:
        return err(f"get_media failed: {exc}")


@tool
def wa_upload_media(file_path: str) -> str:
    """Upload a local file to WhatsApp and return its media id (use that id to send it)."""
    if config.simulating(APP):
        return simulated(APP, "upload_media", file=file_path, media_id="sim-media-1")
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return err(f"File not found: {path}")
        with path.open("rb") as handle:
            data = wa_request(
                "POST", f"{config.WHATSAPP_PHONE_NUMBER_ID}/media",
                files={"file": (path.name, handle, mime_for(str(path)))},
                data={"messaging_product": "whatsapp", "type": mime_for(str(path))},
            )
        return ok(media_id=data.get("id"), file=path.name)
    except Exception as exc:
        return err(f"upload_media failed: {exc}")


@tool
def wa_list_templates(limit: int = 50) -> str:
    """List the message templates in the WhatsApp Business account."""
    if config.simulating(APP):
        return simulated(APP, "list_templates", templates=[{"name": "appointment_reminder", "status": "APPROVED", "language": "en_US"}])
    try:
        data = wa_request("GET", f"{config.WHATSAPP_BUSINESS_ID}/message_templates",
                          params={"limit": max(1, min(int(limit), 200))})
        return ok(count=len(data.get("data", [])), templates=[
            {"name": t.get("name"), "status": t.get("status"), "language": t.get("language"),
             "category": t.get("category"), "id": t.get("id")}
            for t in data.get("data", [])
        ])
    except Exception as exc:
        return err(f"list_templates failed: {exc}")


@tool
def wa_create_template(name: str, body_text: str, category: str = "UTILITY", language_code: str = "en_US", header_text: str = "") -> str:
    """Create a message template (subject to Meta review). category: UTILITY | MARKETING | AUTHENTICATION."""
    if config.simulating(APP):
        return simulated(APP, "create_template", name=name, category=category, status="PENDING")
    try:
        components: list[dict[str, Any]] = []
        if header_text:
            components.append({"type": "HEADER", "format": "TEXT", "text": header_text})
        components.append({"type": "BODY", "text": body_text})
        data = wa_request("POST", f"{config.WHATSAPP_BUSINESS_ID}/message_templates", json={
            "name": re.sub(r"[^a-z0-9_]", "_", name.lower()),
            "language": language_code or "en_US",
            "category": category,
            "components": components,
        })
        return ok(id=data.get("id"), status=data.get("status"), name=name)
    except Exception as exc:
        return err(f"create_template failed: {exc}")


@tool
def wa_delete_template(name: str) -> str:
    """Delete a message template by name."""
    if config.simulating(APP):
        return simulated(APP, "delete_template", name=name)
    try:
        data = wa_request("DELETE", f"{config.WHATSAPP_BUSINESS_ID}/message_templates", params={"name": name})
        return ok(name=name, success=data.get("success", True))
    except Exception as exc:
        return err(f"delete_template failed: {exc}")


@tool
def wa_get_business_profile() -> str:
    """Read the WhatsApp business profile (about, address, description, website, vertical)."""
    if config.simulating(APP):
        return simulated(APP, "get_business_profile", about="We reply in minutes", vertical="OTHER")
    try:
        data = wa_request("GET", f"{config.WHATSAPP_PHONE_NUMBER_ID}/whatsapp_business_profile",
                          params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"})
        return ok(profile=(data.get("data") or [{}])[0])
    except Exception as exc:
        return err(f"get_business_profile failed: {exc}")


@tool
def wa_update_business_profile(
    about: str = "", address: str = "", description: str = "", email: str = "",
    website: str = "", vertical: str = "", profile_picture_url: str = "",
) -> str:
    """Update the business profile. vertical examples: OTHER, RETAIL, PROF_SERVICES, ENTERTAIN, HEALTH, TECH."""
    if config.simulating(APP):
        return simulated(APP, "update_business_profile", about=about[:80], website=website)
    try:
        payload: dict[str, Any] = {"messaging_product": "whatsapp"}
        for key, value in (("about", about), ("address", address), ("description", description),
                           ("email", email), ("vertical", vertical), ("profile_picture_url", profile_picture_url)):
            if value:
                payload[key] = value
        if website:
            payload["websites"] = [website]
        if len(payload) == 1:
            return err("Nothing to update - pass at least one profile field.")
        data = wa_request("POST", f"{config.WHATSAPP_PHONE_NUMBER_ID}/whatsapp_business_profile", json=payload)
        return ok(success=data.get("success", True), updated=list(payload))
    except Exception as exc:
        return err(f"update_business_profile failed: {exc}")


@tool
def wa_list_phone_numbers() -> str:
    """List the phone numbers registered to the WhatsApp Business account."""
    if config.simulating(APP):
        return simulated(APP, "list_phone_numbers", phone_numbers=[
            {"id": config.WHATSAPP_PHONE_NUMBER_ID or "sim-phone-id", "display_phone_number": "+91 98765 43210", "verified_name": "Nexus Ops"}
        ])
    try:
        data = wa_request("GET", f"{config.WHATSAPP_BUSINESS_ID}/phone_numbers")
        return ok(phone_numbers=[
            {"id": p.get("id"), "display_phone_number": p.get("display_phone_number"),
             "verified_name": p.get("verified_name"), "quality_rating": p.get("quality_rating")}
            for p in data.get("data", [])
        ])
    except Exception as exc:
        return err(f"list_phone_numbers failed: {exc}")


WHATSAPP_TOOLS = [
    wa_send_text,
    wa_send_template,
    wa_send_image,
    wa_send_document,
    wa_send_audio,
    wa_send_video,
    wa_send_sticker,
    wa_send_location,
    wa_send_contact_card,
    wa_send_buttons,
    wa_send_list,
    wa_send_cta_button,
    wa_send_reaction,
    wa_mark_read,
    wa_get_media,
    wa_upload_media,
    wa_list_templates,
    wa_create_template,
    wa_delete_template,
    wa_get_business_profile,
    wa_update_business_profile,
    wa_list_phone_numbers,
]
