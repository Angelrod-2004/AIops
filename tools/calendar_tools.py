"""Google Calendar tools - scheduling, free/busy, sharing, recurring events."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from langchain_core.tools import tool

import config
from ._utils import calendar_service, err, ok, parse_dt, simulated, split_csv

APP = "calendar"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _attendees(value: str | list | None) -> list[dict[str, str]]:
    from email.utils import parseaddr

    items = split_csv(value)
    out = []
    for item in items:
        name, addr = parseaddr(item)
        out.append({"email": addr or item, **({"displayName": name} if name else {})})
    return out


def _reminders(minutes: int) -> dict[str, Any]:
    if minutes is None or int(minutes) < 0:
        return {"useDefault": True}
    return {"useDefault": False, "overrides": [{"method": "popup", "minutes": int(minutes)}]}


def _event_card(event: dict[str, Any]) -> dict[str, Any]:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "location": event.get("location", ""),
        "status": event.get("status"),
        "organizer": (event.get("organizer") or {}).get("email"),
        "attendees": [a.get("email") for a in event.get("attendees", []) or []],
        "hangout": event.get("hangoutLink", ""),
        "link": event.get("htmlLink", ""),
    }


def _window(time_min: str, time_max: str) -> tuple[str, str]:
    tz = config.DEFAULT_TIMEZONE
    start_dt = parse_dt(time_min, tz) if time_min and time_min.strip().lower() != "now" else datetime.now(timezone.utc)
    end_dt = parse_dt(time_max, tz) if time_max else start_dt + timedelta(days=7)
    return start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")


def _event_body(
    summary: str | None = None,
    start: str = "",
    end: str = "",
    duration_minutes: int = 60,
    description: str = "",
    location: str = "",
    attendees: str = "",
    timezone_name: str = "",
    recurrence: str = "",
    reminders_minutes: int = 15,
    add_meet: bool = False,
) -> dict[str, Any]:
    zone = timezone_name or config.DEFAULT_TIMEZONE
    body: dict[str, Any] = {}
    if summary:
        body["summary"] = summary
    if start:
        start_dt = parse_dt(start, zone)
        end_dt = parse_dt(end, zone) if end else start_dt + timedelta(minutes=max(1, int(duration_minutes or 60)))
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": zone}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": zone}
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = _attendees(attendees)
    if recurrence:
        rules = [rule.strip() for rule in str(recurrence).replace("\n", ",").split(",") if rule.strip()]
        body["recurrence"] = [rule if rule.upper().startswith("RRULE") else f"RRULE:{rule}" for rule in rules]
    if reminders_minutes is not None and int(reminders_minutes) >= 0:
        body["reminders"] = _reminders(int(reminders_minutes))
    if add_meet:
        body["conferenceData"] = {
            "createRequest": {"requestId": f"nexus-{uuid.uuid4().hex[:12]}", "conferenceSolutionKey": {"type": "hangoutsMeet"}}
        }
    return body


# --------------------------------------------------------------------------- #
# calendars
# --------------------------------------------------------------------------- #
@tool
def calendar_list_calendars(max_results: int = 50) -> str:
    """List every calendar visible to the signed-in account (id, name, access role, primary flag)."""
    if config.simulating(APP):
        return simulated(APP, "list_calendars", calendars=[
            {"id": "primary", "summary": "you@example.com", "primary": True, "accessRole": "owner"},
            {"id": "team@group.calendar.google.com", "summary": "Team", "accessRole": "writer"},
        ])
    try:
        service = calendar_service()
        items = service.calendarList().list(maxResults=max(1, min(int(max_results), 250))).execute().get("items", [])
        calendars = [
            {"id": c.get("id"), "summary": c.get("summary"), "primary": c.get("primary", False),
             "accessRole": c.get("accessRole"), "timeZone": c.get("timeZone")}
            for c in items
        ]
        return ok(count=len(calendars), calendars=calendars)
    except Exception as exc:
        return err(f"list_calendars failed: {exc}")


@tool
def calendar_create_calendar(summary: str, description: str = "", timezone_name: str = "") -> str:
    """Create a brand new secondary calendar."""
    if config.simulating(APP):
        return simulated(APP, "create_calendar", summary=summary, id="sim-cal-1")
    try:
        body = {"summary": summary}
        if description:
            body["description"] = description
        if timezone_name or config.DEFAULT_TIMEZONE:
            body["timeZone"] = timezone_name or config.DEFAULT_TIMEZONE
        cal = calendar_service().calendars().insert(body=body).execute()
        return ok(id=cal.get("id"), summary=cal.get("summary"))
    except Exception as exc:
        return err(f"create_calendar failed: {exc}")


@tool
def calendar_delete_calendar(calendar_id: str) -> str:
    """Delete a secondary calendar (the primary calendar cannot be deleted)."""
    if config.simulating(APP):
        return simulated(APP, "delete_calendar", calendar_id=calendar_id)
    try:
        calendar_service().calendars().delete(calendarId=calendar_id).execute()
        return ok(deleted_calendar=calendar_id)
    except Exception as exc:
        return err(f"delete_calendar failed: {exc}")


@tool
def calendar_list_acl(calendar_id: str = "primary") -> str:
    """List who a calendar is shared with."""
    if config.simulating(APP):
        return simulated(APP, "list_acl", acl=[{"id": "user:ada@example.com", "role": "reader"}])
    try:
        items = calendar_service().acl().list(calendarId=calendar_id).execute().get("items", [])
        return ok(calendar_id=calendar_id, acl=[{"id": i.get("id"), "role": i.get("role"), "scope": i.get("scope")} for i in items])
    except Exception as exc:
        return err(f"list_acl failed: {exc}")


@tool
def calendar_share_calendar(calendar_id: str, email: str, role: str = "reader") -> str:
    """Share a calendar with someone. role: reader | writer | owner | freeBusyReader."""
    if config.simulating(APP):
        return simulated(APP, "share_calendar", calendar_id=calendar_id, email=email, role=role)
    try:
        rule = calendar_service().acl().insert(
            calendarId=calendar_id, body={"role": role, "scope": {"type": "user", "value": email}}
        ).execute()
        return ok(calendar_id=calendar_id, rule_id=rule.get("id"), role=rule.get("role"))
    except Exception as exc:
        return err(f"share_calendar failed: {exc}")


@tool
def calendar_remove_share(calendar_id: str, rule_id: str) -> str:
    """Remove an ACL rule (revoke someone's access). `rule_id` comes from calendar_list_acl."""
    if config.simulating(APP):
        return simulated(APP, "remove_share", calendar_id=calendar_id, rule_id=rule_id)
    try:
        calendar_service().acl().delete(calendarId=calendar_id, ruleId=rule_id).execute()
        return ok(calendar_id=calendar_id, removed_rule=rule_id)
    except Exception as exc:
        return err(f"remove_share failed: {exc}")


# --------------------------------------------------------------------------- #
# events
# --------------------------------------------------------------------------- #
@tool
def calendar_list_events(
    calendar_id: str = "primary",
    time_min: str = "",
    time_max: str = "",
    max_results: int = 10,
    query: str = "",
    single_events: bool = True,
) -> str:
    """List upcoming events. `time_min`/`time_max` accept ISO or natural language ('today', 'next monday'). `query` filters by text."""
    if config.simulating(APP):
        return simulated(APP, "list_events", calendar_id=calendar_id, events=[
            {"id": "sim-ev-1", "summary": "Design review", "start": "2026-10-31T10:00:00+00:00", "end": "2026-10-31T10:30:00+00:00"},
            {"id": "sim-ev-2", "summary": "1:1 with Ada", "start": "2026-10-31T15:00:00+00:00", "end": "2026-10-31T15:30:00+00:00"},
        ])
    try:
        start, end = _window(time_min, time_max)
        response = calendar_service().events().list(
            calendarId=calendar_id,
            timeMin=start,
            timeMax=end,
            maxResults=max(1, min(int(max_results), 250)),
            singleEvents=bool(single_events),
            orderBy="startTime" if single_events else None,
            q=query or None,
        ).execute()
        events = [_event_card(e) for e in response.get("items", [])]
        return ok(calendar_id=calendar_id, window={"from": start, "to": end}, count=len(events), events=events)
    except Exception as exc:
        return err(f"list_events failed: {exc}")


@tool
def calendar_search_events(query: str, calendar_id: str = "primary", time_min: str = "", time_max: str = "", max_results: int = 10) -> str:
    """Search events by text (title, description, location)."""
    return calendar_list_events.invoke({
        "query": query, "calendar_id": calendar_id, "time_min": time_min,
        "time_max": time_max, "max_results": max_results,
    })


@tool
def calendar_get_event(event_id: str, calendar_id: str = "primary") -> str:
    """Fetch one event with description, attendees and conference link."""
    if config.simulating(APP):
        return simulated(APP, "get_event", id=event_id, summary="Design review")
    try:
        event = calendar_service().events().get(calendarId=calendar_id, eventId=event_id).execute()
        return ok(event={**_event_card(event), "description": event.get("description", ""),
                         "recurrence": event.get("recurrence", []),
                         "reminders": event.get("reminders", {})})
    except Exception as exc:
        return err(f"get_event failed: {exc}")


@tool
def calendar_create_event(
    summary: str,
    start: str,
    end: str = "",
    duration_minutes: int = 60,
    calendar_id: str = "primary",
    description: str = "",
    location: str = "",
    attendees: str = "",
    timezone_name: str = "",
    recurrence: str = "",
    reminders_minutes: int = 15,
    add_meet: bool = False,
) -> str:
    """Create an event. Give `end` or let `duration_minutes` compute it. `recurrence` takes RRULEs e.g. 'RRULE:FREQ=WEEKLY;BYDAY=MO'. add_meet=True attaches a Google Meet link."""
    if config.simulating(APP):
        return simulated(APP, "create_event", summary=summary, start=start, duration_minutes=duration_minutes,
                         attendees=split_csv(attendees), meet=add_meet, id="sim-ev-new")
    try:
        body = _event_body(summary, start, end, duration_minutes, description, location, attendees,
                           timezone_name, recurrence, reminders_minutes, add_meet)
        event = calendar_service().events().insert(
            calendarId=calendar_id, body=body, conferenceDataVersion=1 if add_meet else 0,
            sendUpdates="all" if attendees else "none",
        ).execute()
        return ok(event=_event_card(event), meet=event.get("hangoutLink", ""))
    except Exception as exc:
        return err(f"create_event failed: {exc}")


@tool
def calendar_update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str = "",
    start: str = "",
    end: str = "",
    duration_minutes: int = 0,
    description: str = "",
    location: str = "",
    attendees: str = "",
    timezone_name: str = "",
    recurrence: str = "",
    reminders_minutes: int = -1,
    add_meet: bool = False,
) -> str:
    """Patch an existing event - only the fields you pass are changed. Moving the event only needs `start` (plus optional duration_minutes)."""
    if config.simulating(APP):
        return simulated(APP, "update_event", id=event_id, summary=summary, start=start)
    try:
        body = _event_body(summary or None, start, end, duration_minutes or 60, description, location,
                           attendees, timezone_name, recurrence, reminders_minutes, add_meet)
        for key in ("description", "location", "recurrence"):
            if key in body and body[key] in ("", [], None):
                body.pop(key)
        if not body.get("start") and "description" not in body and "location" not in body and "summary" not in body:
            return err("Nothing to update - pass at least one field.")
        event = calendar_service().events().patch(
            calendarId=calendar_id, eventId=event_id, body=body,
            conferenceDataVersion=1 if add_meet else 0, sendUpdates="all" if attendees else "none",
        ).execute()
        return ok(event=_event_card(event), meet=event.get("hangoutLink", ""))
    except Exception as exc:
        return err(f"update_event failed: {exc}")


@tool
def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> str:
    """Delete (cancel) an event."""
    if config.simulating(APP):
        return simulated(APP, "delete_event", id=event_id)
    try:
        calendar_service().events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates="all").execute()
        return ok(deleted_event=event_id)
    except Exception as exc:
        return err(f"delete_event failed: {exc}")


@tool
def calendar_quick_add(text: str, calendar_id: str = "primary") -> str:
    """Create an event from one plain-English line, e.g. 'Lunch with Priya tomorrow 1pm-2pm at Cafe Mocha'."""
    if config.simulating(APP):
        return simulated(APP, "quick_add", text=text, id="sim-ev-quick")
    try:
        event = calendar_service().events().quickAdd(calendarId=calendar_id, text=text).execute()
        return ok(event=_event_card(event))
    except Exception as exc:
        return err(f"quick_add failed: {exc}")


@tool
def calendar_move_event(event_id: str, destination_calendar_id: str, calendar_id: str = "primary") -> str:
    """Move an event from one calendar to another."""
    if config.simulating(APP):
        return simulated(APP, "move_event", id=event_id, destination=destination_calendar_id)
    try:
        event = calendar_service().events().move(
            calendarId=calendar_id, eventId=event_id, destination=destination_calendar_id
        ).execute()
        return ok(event=_event_card(event), moved_to=destination_calendar_id)
    except Exception as exc:
        return err(f"move_event failed: {exc}")


@tool
def calendar_list_instances(event_id: str, calendar_id: str = "primary", max_results: int = 20, show_cancelled: bool = False) -> str:
    """List the occurrences of a recurring event."""
    if config.simulating(APP):
        return simulated(APP, "list_instances", id=event_id, instances=[{"id": "sim-inst-1", "start": "2026-11-02T10:00:00Z"}])
    try:
        response = calendar_service().events().instances(
            calendarId=calendar_id, eventId=event_id, maxResults=max(1, min(int(max_results), 250)),
            showDeleted=bool(show_cancelled),
        ).execute()
        return ok(count=len(response.get("items", [])), instances=[_event_card(e) for e in response.get("items", [])])
    except Exception as exc:
        return err(f"list_instances failed: {exc}")


@tool
def calendar_add_attendees(event_id: str, attendees: str, calendar_id: str = "primary") -> str:
    """Add extra guests to an event (comma separated emails). Existing guests are kept and notified."""
    if config.simulating(APP):
        return simulated(APP, "add_attendees", id=event_id, added=split_csv(attendees))
    try:
        service = calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        existing = {a.get("email", "").lower(): a for a in event.get("attendees", []) or []}
        for guest in _attendees(attendees):
            existing.setdefault(guest["email"].lower(), guest)
        event["attendees"] = list(existing.values())
        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event, sendUpdates="all").execute()
        return ok(event=_event_card(updated))
    except Exception as exc:
        return err(f"add_attendees failed: {exc}")


@tool
def calendar_rsvp(event_id: str, response: str = "accepted", calendar_id: str = "primary") -> str:
    """Respond to an invitation. response: accepted | declined | tentative."""
    if config.simulating(APP):
        return simulated(APP, "rsvp", id=event_id, response=response)
    try:
        service = calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        guests = event.get("attendees", []) or []
        target = next((a for a in guests if a.get("self")), None)
        if target is None:
            email = service.calendars().get(calendarId=calendar_id).execute().get("id", "").lower()
            target = next((a for a in guests if a.get("email", "").lower() == email), None)
            if target is None:
                target = {"email": email}
                guests.append(target)
        target["responseStatus"] = response
        event["attendees"] = guests
        updated = service.events().patch(calendarId=calendar_id, eventId=event_id, body={"attendees": guests}).execute()
        return ok(event=_event_card(updated), response=response)
    except Exception as exc:
        return err(f"rsvp failed: {exc}")


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
@tool
def calendar_freebusy(time_min: str = "", time_max: str = "", calendars: str = "primary") -> str:
    """Return the busy blocks for one or more calendars between two times."""
    if config.simulating(APP):
        return simulated(APP, "freebusy", busy=[{"calendar": "primary", "start": "2026-10-31T10:00:00Z", "end": "2026-10-31T10:30:00Z"}])
    try:
        start, end = _window(time_min, time_max)
        items = [{"id": c} for c in split_csv(calendars)]
        result = calendar_service().freebusy().query(body={"timeMin": start, "timeMax": end, "items": items}).execute()
        busy = []
        for cal_id, data in (result.get("calendars") or {}).items():
            for block in data.get("busy", []) or []:
                busy.append({"calendar": cal_id, "start": block.get("start"), "end": block.get("end")})
        return ok(window={"from": start, "to": end}, busy=busy)
    except Exception as exc:
        return err(f"freebusy failed: {exc}")


@tool
def calendar_find_free_slots(
    time_min: str = "",
    time_max: str = "",
    duration_minutes: int = 30,
    calendars: str = "primary",
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    max_slots: int = 5,
    timezone_name: str = "",
) -> str:
    """Find open meeting slots that fit `duration_minutes` inside working hours, ignoring everyone's busy blocks."""
    if config.simulating(APP):
        return simulated(APP, "find_free_slots", slots=[
            {"start": "2026-10-31T09:00:00+00:00", "end": "2026-10-31T09:30:00+00:00"},
            {"start": "2026-10-31T11:00:00+00:00", "end": "2026-10-31T11:30:00+00:00"},
            {"start": "2026-10-31T14:30:00+00:00", "end": "2026-10-31T15:00:00+00:00"},
        ])
    try:
        zone = timezone_name or config.DEFAULT_TIMEZONE
        start, end = _window(time_min or "now", time_max)
        items = [{"id": c} for c in split_csv(calendars)]
        result = calendar_service().freebusy().query(body={"timeMin": start, "timeMax": end, "items": items}).execute()
        busy: list[tuple[datetime, datetime]] = []
        for data in (result.get("calendars") or {}).values():
            for block in data.get("busy", []) or []:
                busy.append((parse_dt(block["start"], zone), parse_dt(block["end"], zone)))
        busy.sort(key=lambda span: span[0])

        duration = max(5, int(duration_minutes))
        cursor = parse_dt(start, zone)
        limit = parse_dt(end, zone)
        now = datetime.now(timezone.utc)
        if cursor < now:
            cursor = now
        cursor = cursor.replace(minute=(cursor.minute // 15) * 15, second=0, microsecond=0)
        slots: list[dict[str, str]] = []
        while cursor + timedelta(minutes=duration) <= limit and len(slots) < max(1, int(max_slots)):
            slot_end = cursor + timedelta(minutes=duration)
            outside_hours = not (int(work_start_hour) <= cursor.hour < int(work_end_hour))
            overlaps = any(cursor < b_end and slot_end > b_start for b_start, b_end in busy)
            if not outside_hours and not overlaps:
                slots.append({"start": cursor.isoformat(), "end": slot_end.isoformat()})
                cursor = slot_end
            else:
                cursor += timedelta(minutes=15)
        return ok(count=len(slots), slots=slots, busy_blocks=len(busy), window={"from": start, "to": end})
    except Exception as exc:
        return err(f"find_free_slots failed: {exc}")


CALENDAR_TOOLS = [
    calendar_list_calendars,
    calendar_create_calendar,
    calendar_delete_calendar,
    calendar_list_acl,
    calendar_share_calendar,
    calendar_remove_share,
    calendar_list_events,
    calendar_search_events,
    calendar_get_event,
    calendar_create_event,
    calendar_update_event,
    calendar_delete_event,
    calendar_quick_add,
    calendar_move_event,
    calendar_list_instances,
    calendar_add_attendees,
    calendar_rsvp,
    calendar_freebusy,
    calendar_find_free_slots,
]
