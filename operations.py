"""The operation catalogue - the single source of truth the UI renders from.

Every entry maps a human-friendly operation onto exactly one LangChain tool.
Field names match the tool's parameter names 1:1, so a filled form can be
executed deterministically (no LLM) or handed to an agent as a plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import config


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"  # text | textarea | number | toggle | select | json | datetime | csv | file
    required: bool = False
    options: tuple[str, ...] = ()
    default: Any = None
    help: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class Operation:
    id: str
    app: str
    name: str
    tool: str
    summary: str
    fields: tuple[Field, ...] = ()
    group: str = "General"
    example: str = ""

    @property
    def required_fields(self) -> list[Field]:
        return [f for f in self.fields if f.required]


# --------------------------------------------------------------------------- #
# reusable field definitions
# --------------------------------------------------------------------------- #
F_TO_EMAIL = Field("to", "To", required=True, placeholder="ada@example.com",
                   help="Comma separated. `Ada Lovelace <ada@example.com>` works too.")
F_CC = Field("cc", "Cc", placeholder="ops@example.com")
F_BCC = Field("bcc", "Bcc", placeholder="archive@example.com")
F_SUBJECT = Field("subject", "Subject", required=True, placeholder="Q4 planning - action needed")
F_BODY = Field("body", "Body", kind="textarea", required=True, placeholder="Hi Ada,\n\n…")
F_HTML = Field("html", "Send as HTML", kind="toggle", default=False, help="Treat the body as rich HTML.")
F_ATTACH = Field("attachments", "Attachments", kind="file",
                 placeholder="C:/reports/q4.pdf, C:/reports/data.xlsx", help="Local file paths, comma separated.")
F_MSG_ID = Field("message_id", "Message id", required=True, placeholder="18c1f2a9b0d4e5f6",
                 help="Copy it from a list/read operation.")
F_MAX = Field("max_results", "Max results", kind="number", default=10,
              options=(5, 10, 20, 25, 50, 100), help="1-100.")
F_QUERY_GMAIL = Field("query", "Gmail query", placeholder="from:ada is:unread newer_than:7d",
                      help="Gmail search syntax.")
F_LABEL_ID = Field("label", "Label", kind="select", default="",
                   options=("", "INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH"),
                   help="Optional label id or system label.")
F_TEXT = Field("text", "Plain-English line", required=True, kind="textarea",
               placeholder="Lunch with Priya tomorrow 1pm-2pm at Cafe Mocha")

F_CAL_ID = Field("calendar_id", "Calendar", default="primary", placeholder="primary",
                 help="`primary` or a calendar id from List calendars.")
F_TIME_MIN = Field("time_min", "From", kind="datetime", placeholder="today 09:00",
                   help="Pick date and time or leave blank for now.")
F_TIME_MAX = Field("time_max", "To", kind="datetime", placeholder="+7 days",
                   help="Pick date and time or defaults to 7 days after `From`.")
F_EVENT_ID = Field("event_id", "Event id", required=True, placeholder="4q1k2j3h4g5f6d7s")
F_ATTENDEES = Field("attendees", "Guests", placeholder="ada@example.com, raj@example.com",
                    help="Comma separated emails or `Name <email>`.")
F_TZ = Field("timezone_name", "Timezone", kind="select", default="",
             options=("", "Asia/Kolkata", "UTC", "America/New_York", "America/Los_Angeles",
                      "America/Chicago", "Europe/London", "Europe/Paris", "Europe/Berlin",
                      "Asia/Dubai", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney"),
             help="IANA name. Defaults to CALENDAR_TIMEZONE.")
F_SUMMARY = Field("summary", "Title", required=True, placeholder="Design review")
F_START = Field("start", "Start", kind="datetime", required=True, placeholder="tomorrow 15:00")
F_END = Field("end", "End", kind="datetime", placeholder="tomorrow 15:45", help="Leave blank to use duration.")
F_LOCATION = Field("location", "Location", placeholder="Meet / Room 4B / Cafe Mocha")
F_DESC = Field("description", "Description", kind="textarea", placeholder="Agenda…")
F_RECUR = Field("recurrence", "Repeat (RRULE)", kind="select", default="",
                options=("", "RRULE:FREQ=DAILY", "RRULE:FREQ=WEEKLY",
                         "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "RRULE:FREQ=MONTHLY", "RRULE:FREQ=YEARLY"),
                help="Choose repetition schedule.")
F_REMIND = Field("reminders_minutes", "Reminder (min before)", kind="number", default=15,
                 options=(0, 5, 10, 15, 30, 60, 120, 1440))
F_MEET = Field("add_meet", "Add Google Meet link", kind="toggle", default=False)

F_JQL = Field("jql", "JQL", required=True, kind="textarea",
              placeholder="project = OPS AND status != Done ORDER BY updated DESC")
F_ISSUE_KEY = Field("issue_key", "Issue key", required=True, placeholder="OPS-42")
F_PROJECT = Field("project_key", "Project key", default=getattr(config, "JIRA_DEFAULT_PROJECT", "") or "OPS",
                  placeholder="OPS", help="Defaults to JIRA_DEFAULT_PROJECT.")
F_PROJECT_REQ = Field("project_key", "Project key", required=True,
                      default=getattr(config, "JIRA_DEFAULT_PROJECT", "") or "OPS", placeholder="OPS")
F_ISSUE_TYPE = Field("issue_type", "Issue type", kind="select", default="Task",
                     options=("Task", "Bug", "Story", "Epic", "Sub-task"), help="Task, Bug, Story, Epic, Sub-task…")
F_ASSIGNEE = Field("assignee", "Assignee", placeholder="ada@example.com", help="Email, display name or accountId.")
F_PRIORITY = Field("priority", "Priority", kind="select", default="Medium",
                   options=("Medium", "Highest", "High", "Low", "Lowest"))
F_LABELS = Field("labels", "Labels", placeholder="infra, sev2", help="Comma separated.")
F_DUE = Field("due_date", "Due date", kind="date", placeholder="2026-11-05")
F_COMMENT = Field("comment", "Comment", kind="textarea", placeholder="Root cause: connection pool exhausted…")
F_FILE = Field("file_path", "File", kind="file", required=True, placeholder="C:/logs/trace.txt")
F_STORY_POINTS = Field("story_points", "Story points", kind="number")

F_WA_TO = Field("to", "Recipient", required=True, default="",
                placeholder="919876543210", help="Digits with country code, no '+' or spaces.")
F_WA_TEXT = Field("body_text", "Message", kind="textarea", required=True, placeholder="Deploy finished - all green ✅")
F_WA_URL = Field("url", "Public URL", placeholder="https://…/chart.png")
F_WA_BUTTONS = Field("buttons_json", "Buttons (JSON)", kind="json", required=True,
                     placeholder='[{"id":"yes","title":"Approve"},{"id":"no","title":"Reject"}]',
                     help="Max 3 buttons, titles <= 20 chars.")
F_WA_SECTIONS = Field("sections_json", "Sections (JSON)", kind="json", required=True,
                      placeholder='[{"title":"Slots","rows":[{"id":"9am","title":"9:00 AM","description":"Free"}]}]',
                      help="Max 10 rows in total.")


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def _f(*items: Field) -> tuple[Field, ...]:
    return tuple(items)


OPERATIONS: list[Operation] = []


def op(
    oid: str,
    app: str,
    name: str,
    tool: str,
    summary: str,
    fields: Iterable[Field] = (),
    group: str = "General",
    example: str = "",
) -> None:
    OPERATIONS.append(Operation(oid, app, name, tool, summary, tuple(fields), group, example))


# =========================================================================== #
# GMAIL
# =========================================================================== #
op("gmail_send", "gmail", "Send email", "gmail_send_message",
   "Compose and deliver a new email, with optional cc/bcc, HTML body and attachments.",
   _f(F_TO_EMAIL, F_SUBJECT, F_BODY, F_CC, F_BCC, F_HTML, F_ATTACH), "Compose",
   "Email the Q4 deck to ada@example.com with subject 'Q4 planning'")
op("gmail_reply", "gmail", "Reply to a message", "gmail_reply_message",
   "Reply inside the original thread, optionally to every recipient.",
   _f(F_MSG_ID, F_BODY, Field("html", "Send as HTML", kind="toggle", default=False),
      Field("reply_all", "Reply all", kind="toggle", default=False)), "Compose",
   "Reply to that thread saying the numbers look good")
op("gmail_forward", "gmail", "Forward a message", "gmail_forward_message",
   "Forward a message, keeping the original attachments.",
   _f(F_MSG_ID, F_TO_EMAIL, Field("note", "Note", kind="textarea", placeholder="FYI - see below."),
      Field("include_attachments", "Include attachments", kind="toggle", default=True)), "Compose")
op("gmail_create_draft", "gmail", "Create draft", "gmail_create_draft",
   "Save an email as a draft so you can review it before sending.",
   _f(F_TO_EMAIL, F_SUBJECT, F_BODY, F_CC, F_BCC, F_HTML, F_ATTACH), "Compose")
op("gmail_send_draft", "gmail", "Send draft", "gmail_send_draft",
   "Send an existing draft by its id.",
   _f(Field("draft_id", "Draft id", required=True, placeholder="r-1234567890")), "Compose")
op("gmail_list_drafts", "gmail", "List drafts", "gmail_list_drafts", "List saved drafts.",
   _f(F_MAX), "Compose")
op("gmail_delete_draft", "gmail", "Delete draft", "gmail_delete_draft", "Delete a draft permanently.",
   _f(Field("draft_id", "Draft id", required=True)), "Compose")

op("gmail_list", "gmail", "List recent mail", "gmail_list_messages",
   "Show the latest messages, optionally filtered by a Gmail query or label.",
   _f(F_QUERY_GMAIL, F_LABEL_ID, F_MAX), "Inbox",
   "Show my 5 most recent unread emails")
op("gmail_search", "gmail", "Search mail", "gmail_search_messages",
   "Full Gmail query syntax - senders, dates, attachments, labels.",
   _f(Field("query", "Gmail query", required=True, placeholder="has:attachment from:finance after:2026/01/01"), F_MAX),
   "Inbox", "Find every invoice from finance this month")
op("gmail_read", "gmail", "Read a message", "gmail_read_message",
   "Open one message: headers, plain-text body and the attachment list.",
   _f(F_MSG_ID), "Inbox")
op("gmail_mark_read", "gmail", "Mark as read", "gmail_mark_read", "Remove the UNREAD label.",
   _f(F_MSG_ID), "Inbox")
op("gmail_mark_unread", "gmail", "Mark as unread", "gmail_mark_unread", "Put the UNREAD label back.",
   _f(F_MSG_ID), "Inbox")
op("gmail_trash", "gmail", "Move to trash", "gmail_trash_message", "Recoverable delete.",
   _f(F_MSG_ID), "Inbox")
op("gmail_untrash", "gmail", "Restore from trash", "gmail_untrash_message", "Bring a trashed message back to the inbox.",
   _f(F_MSG_ID), "Inbox")
op("gmail_delete", "gmail", "Delete permanently", "gmail_delete_message",
   "Bypasses Trash. This cannot be undone.", _f(F_MSG_ID), "Inbox")
op("gmail_modify_labels", "gmail", "Change labels", "gmail_modify_labels",
   "Add and/or remove labels on a message.",
   _f(F_MSG_ID, Field("add", "Add labels", kind="multiselect",
                      options=("STARRED", "IMPORTANT", "UNREAD", "INBOX", "SPAM", "TRASH")),
      Field("remove", "Remove labels", kind="multiselect",
            options=("INBOX", "UNREAD", "STARRED", "IMPORTANT", "SPAM", "TRASH"))), "Labels")
op("gmail_list_labels", "gmail", "List labels", "gmail_list_labels", "Every label with its id and type.",
   (), "Labels")
op("gmail_create_label", "gmail", "Create label", "gmail_create_label", "Add a new label to the mailbox.",
   _f(Field("name", "Label name", required=True, placeholder="Clients")), "Labels")
op("gmail_delete_label", "gmail", "Delete label", "gmail_delete_label", "Remove a label by id.",
   _f(Field("label_id", "Label id", required=True, placeholder="Label_123")), "Labels")
op("gmail_list_threads", "gmail", "List threads", "gmail_list_threads", "Conversation-level view of the mailbox.",
   _f(F_QUERY_GMAIL, F_MAX), "Conversations")
op("gmail_get_thread", "gmail", "Read a thread", "gmail_get_thread", "Every message in one conversation.",
   _f(Field("thread_id", "Thread id", required=True)), "Conversations")
op("gmail_trash_thread", "gmail", "Trash a thread", "gmail_trash_thread", "Move a whole conversation to Trash.",
   _f(Field("thread_id", "Thread id", required=True)), "Conversations")
op("gmail_delete_thread", "gmail", "Delete a thread", "gmail_delete_thread", "Permanently delete a conversation.",
   _f(Field("thread_id", "Thread id", required=True)), "Conversations")
op("gmail_download_attachment", "gmail", "Download attachment", "gmail_download_attachment",
   "Save one attachment to disk.",
   _f(F_MSG_ID, Field("attachment_id", "Attachment id", required=True),
      Field("save_path", "Save to", kind="file", required=True, placeholder="C:/downloads/q4.pdf")), "Attachments")
op("gmail_profile", "gmail", "Mailbox profile", "gmail_get_profile", "Signed-in address and mailbox totals.",
   (), "Account")

# =========================================================================== #
# GOOGLE CALENDAR
# =========================================================================== #
op("cal_list_events", "calendar", "List events", "calendar_list_events",
   "Upcoming events for a calendar inside a time window.",
   _f(F_CAL_ID, F_TIME_MIN, F_TIME_MAX, F_MAX,
      Field("query", "Search text", placeholder="design review"),
      Field("single_events", "Expand recurring", kind="toggle", default=True)), "Read",
   "What's on my calendar tomorrow?")
op("cal_search_events", "calendar", "Search events", "calendar_search_events",
   "Free-text search across event titles, descriptions and locations.",
   _f(Field("query", "Search text", required=True, placeholder="standup"), F_CAL_ID, F_TIME_MIN, F_TIME_MAX, F_MAX),
   "Read")
op("cal_get_event", "calendar", "Get event", "calendar_get_event", "Full details of one event.",
   _f(F_EVENT_ID, F_CAL_ID), "Read")
op("cal_create_event", "calendar", "Create event", "calendar_create_event",
   "Book something new - guests, location, Meet link, reminders and recurrence.",
   _f(F_SUMMARY, F_START, F_END,
      Field("duration_minutes", "Duration (min)", kind="number", default=60,
            options=(15, 30, 45, 60, 90, 120, 180, 240, 480)),
      F_CAL_ID, F_DESC, F_LOCATION, F_ATTENDEES, F_TZ, F_RECUR, F_REMIND, F_MEET), "Write",
   "Schedule a design review tomorrow at 3pm with ada@example.com and add a Meet link")
op("cal_update_event", "calendar", "Update event", "calendar_update_event",
   "Patch an event - only the fields you fill in change. Moving it just needs `Start`.",
   _f(F_EVENT_ID, F_CAL_ID, Field("summary", "New title"),
      Field("start", "Start", kind="datetime", placeholder="tomorrow 11:00", help="Set this to move the event."),
      F_END,
      Field("duration_minutes", "Duration (min)", kind="number", default=60,
            options=(15, 30, 45, 60, 90, 120, 180, 240, 480)),
      F_DESC, F_LOCATION, F_ATTENDEES, F_TZ, F_RECUR,
      Field("reminders_minutes", "Reminder (min)", kind="number", default=-1,
            options=(-1, 0, 5, 10, 15, 30, 60, 120, 1440),
            help="-1 keeps the current reminders."), F_MEET), "Write",
   "Move the design review to Friday 11am")
op("cal_delete_event", "calendar", "Delete event", "calendar_delete_event", "Cancel an event and notify guests.",
   _f(F_EVENT_ID, F_CAL_ID), "Write")
op("cal_quick_add", "calendar", "Quick add (plain English)", "calendar_quick_add",
   "Google parses one sentence into a full event.",
   _f(F_TEXT, F_CAL_ID), "Write",
   "Lunch with Priya tomorrow 1pm-2pm at Cafe Mocha")
op("cal_move_event", "calendar", "Move event to another calendar", "calendar_move_event",
   "Relocate an event without duplicating it.",
   _f(F_EVENT_ID, Field("destination_calendar_id", "Destination calendar", required=True,
                        placeholder="team@group.calendar.google.com"), F_CAL_ID), "Write")
op("cal_instances", "calendar", "List recurring instances", "calendar_list_instances",
   "Every occurrence of a recurring event.",
   _f(F_EVENT_ID, F_CAL_ID, F_MAX, Field("show_cancelled", "Include cancelled", kind="toggle", default=False)), "Write")
op("cal_add_attendees", "calendar", "Invite more guests", "calendar_add_attendees",
   "Add attendees to an existing event and notify everyone.",
   _f(F_EVENT_ID, Field("attendees", "Guests", required=True, placeholder="ada@example.com"), F_CAL_ID), "Guests")
op("cal_rsvp", "calendar", "RSVP", "calendar_rsvp", "Accept, decline or tentatively accept an invitation.",
   _f(F_EVENT_ID, Field("response", "Response", kind="select", default="accepted",
                        options=("accepted", "declined", "tentative")), F_CAL_ID), "Guests")
op("cal_free_slots", "calendar", "Find free slots", "calendar_find_free_slots",
   "Intersect busy blocks across calendars and propose open slots inside working hours.",
   _f(F_TIME_MIN, F_TIME_MAX,
      Field("duration_minutes", "Meeting length (min)", kind="number", default=30,
            options=(15, 30, 45, 60, 90, 120)),
      Field("calendars", "Calendars", placeholder="primary, ada@example.com", help="Comma separated calendar ids."),
      Field("work_start_hour", "Work starts (0-23)", kind="number", default=9, options=tuple(range(6, 13))),
      Field("work_end_hour", "Work ends (0-23)", kind="number", default=18, options=tuple(range(13, 23))),
      Field("max_slots", "Max slots", kind="number", default=5, options=(3, 5, 10, 15, 20)), F_TZ), "Availability",
   "Find a free 30 minute slot with ada@example.com tomorrow afternoon")
op("cal_freebusy", "calendar", "Busy blocks", "calendar_freebusy", "Raw busy times across calendars.",
   _f(F_TIME_MIN, F_TIME_MAX,
      Field("calendars", "Calendars", default="primary", placeholder="primary, ada@example.com")), "Availability")
op("cal_list_calendars", "calendar", "List calendars", "calendar_list_calendars", "Every calendar you can see.",
   _f(Field("max_results", "Max results", kind="number", default=50, options=(10, 25, 50, 100))), "Calendars")
op("cal_create_calendar", "calendar", "Create calendar", "calendar_create_calendar", "Add a secondary calendar.",
   _f(Field("summary", "Name", required=True, placeholder="Team Ops"), F_DESC, F_TZ), "Calendars")
op("cal_delete_calendar", "calendar", "Delete calendar", "calendar_delete_calendar",
   "Remove a secondary calendar (primary cannot be deleted).",
   _f(Field("calendar_id", "Calendar id", required=True)), "Calendars")
op("cal_list_acl", "calendar", "List sharing", "calendar_list_acl", "Who has access to a calendar.",
   _f(F_CAL_ID), "Sharing")
op("cal_share", "calendar", "Share calendar", "calendar_share_calendar", "Grant someone access to a calendar.",
   _f(F_CAL_ID, Field("email", "Email", required=True, placeholder="ada@example.com"),
      Field("role", "Role", kind="select", default="reader",
            options=("reader", "writer", "owner", "freeBusyReader"))), "Sharing")
op("cal_remove_share", "calendar", "Revoke sharing", "calendar_remove_share", "Remove an ACL rule.",
   _f(F_CAL_ID, Field("rule_id", "Rule id", required=True, placeholder="user:ada@example.com")), "Sharing")

# =========================================================================== #
# JIRA
# =========================================================================== #
op("jira_create_issue", "jira", "Create issue", "jira_create_issue",
   "File a task, bug, story or epic with assignee, priority, labels and due date.",
   _f(F_SUMMARY, F_PROJECT, F_ISSUE_TYPE, F_DESC, F_ASSIGNEE, F_PRIORITY, F_LABELS, F_DUE,
      Field("parent_key", "Parent key", placeholder="OPS-100")), "Write",
   "Create a bug in OPS called 'Checkout latency spike', assign it to ada, priority High")
op("jira_update_issue", "jira", "Update issue", "jira_update_issue",
   "Change the fields of an existing issue.",
   _f(F_ISSUE_KEY, Field("summary", "New summary"), F_DESC, F_ASSIGNEE, F_PRIORITY, F_LABELS, F_DUE, F_ISSUE_TYPE),
   "Write")
op("jira_transition", "jira", "Move to another status", "jira_transition_issue",
   "Run a workflow transition by name or id, with an optional comment.",
   _f(F_ISSUE_KEY, Field("transition", "Transition", required=True, kind="select", default="In Progress",
                         options=("In Progress", "Done", "To Do", "In Review", "Under Review", "Blocked", "Closed"),
                         help="Name or id - workflow status."), F_COMMENT), "Write",
   "Move OPS-42 to In Progress and comment that I'm investigating")
op("jira_add_comment", "jira", "Comment", "jira_add_comment", "Add a comment to an issue.",
   _f(F_ISSUE_KEY, F_COMMENT), "Write")
op("jira_assign", "jira", "Assign", "jira_assign_issue", "Assign an issue to a teammate.",
   _f(F_ISSUE_KEY, Field("assignee", "Assignee", required=True, placeholder="ada@example.com")), "Write")
op("jira_add_attachment", "jira", "Attach a file", "jira_add_attachment", "Upload a local file to an issue.",
   _f(F_ISSUE_KEY, F_FILE), "Write")
op("jira_worklog", "jira", "Log work", "jira_add_worklog", "Record time spent on an issue.",
   _f(F_ISSUE_KEY, Field("time_spent", "Time spent", required=True, kind="select", default="1h",
                         options=("15m", "30m", "45m", "1h", "1h 30m", "2h", "2h 30m", "3h", "4h", "1d")),
      F_COMMENT, Field("started", "Started", kind="datetime", placeholder="2026-10-30T09:00:00")), "Write")
op("jira_link", "jira", "Link two issues", "jira_link_issues",
   "Create an issue link such as Blocks / Relates / Duplicate.",
   _f(Field("outward_issue", "Outward issue", required=True, placeholder="OPS-1"),
      Field("inward_issue", "Inward issue", required=True, placeholder="OPS-2"),
      Field("link_type", "Link type", default="Blocks",
            options=("Blocks", "Cloners", "Duplicate", "Relates"), kind="select"), F_COMMENT), "Write")
op("jira_watcher_add", "jira", "Add watcher", "jira_add_watcher", "Notify someone about an issue.",
   _f(F_ISSUE_KEY, Field("user", "User", required=True, placeholder="ada@example.com")), "Write")
op("jira_watcher_remove", "jira", "Remove watcher", "jira_remove_watcher", "Stop notifying someone.",
   _f(F_ISSUE_KEY, Field("account_id", "Account id", required=True)), "Write")
op("jira_delete_issue", "jira", "Delete issue", "jira_delete_issue",
   "Permanently delete an issue (optionally with subtasks).",
   _f(F_ISSUE_KEY, Field("delete_subtasks", "Delete subtasks", kind="toggle", default=False)), "Write")
op("jira_search", "jira", "Search (JQL)", "jira_search", "Run any JQL query.",
   _f(F_JQL, F_MAX, Field("fields", "Fields", placeholder="summary,status,assignee")), "Read",
   "Show me all high priority bugs in OPS that are not done")
op("jira_get_issue", "jira", "Get issue", "jira_get_issue", "One issue with description and metadata.",
   _f(F_ISSUE_KEY), "Read")
op("jira_transitions", "jira", "List transitions", "jira_list_transitions", "Valid next statuses for an issue.",
   _f(F_ISSUE_KEY), "Read")
op("jira_comments", "jira", "List comments", "jira_get_comments", "All comments on an issue.",
   _f(F_ISSUE_KEY, F_MAX), "Read")
op("jira_update_comment", "jira", "Edit comment", "jira_update_comment", "Change the text of your comment.",
   _f(F_ISSUE_KEY, Field("comment_id", "Comment id", required=True), F_COMMENT), "Read")
op("jira_delete_comment", "jira", "Delete comment", "jira_delete_comment", "Remove a comment.",
   _f(F_ISSUE_KEY, Field("comment_id", "Comment id", required=True)), "Read")
op("jira_projects", "jira", "List projects", "jira_list_projects", "Every project you can see.",
   _f(Field("limit", "Limit", kind="number", default=50, options=(10, 25, 50, 100))), "Discover")
op("jira_project", "jira", "Project details", "jira_get_project",
   "Issue types and workflow statuses for one project.",
   _f(Field("project_key", "Project key", required=True, placeholder="OPS")), "Discover")
op("jira_users", "jira", "Find users", "jira_list_users", "Look up accountIds before assigning.",
   _f(Field("query", "Query", required=True, placeholder="ada"),
      Field("limit", "Limit", kind="number", default=10, options=(5, 10, 20, 50))),
   "Discover")
op("jira_boards", "jira", "List boards", "jira_list_boards", "Agile boards in the site.",
   _f(Field("limit", "Limit", kind="number", default=20, options=(10, 20, 50, 100))), "Agile")
op("jira_sprints", "jira", "List sprints", "jira_list_sprints", "Sprints on a board.",
   _f(Field("board_id", "Board id", kind="number", required=True, default=1),
      Field("state", "State", kind="select", default="active,future",
            options=("active,future", "active", "future", "closed"))), "Agile")
op("jira_create_sprint", "jira", "Create sprint", "jira_create_sprint", "Start a new sprint on a board.",
   _f(Field("name", "Name", required=True, placeholder="Sprint 15"),
      Field("board_id", "Board id", kind="number", required=True, default=1),
      Field("start_date", "Start", kind="datetime"), Field("end_date", "End", kind="datetime"),
      Field("goal", "Goal", kind="textarea")), "Agile")
op("jira_sprint_issues", "jira", "Sprint contents", "jira_sprint_issues", "Issues inside a sprint.",
   _f(Field("sprint_id", "Sprint id", kind="number", required=True, default=7), F_MAX), "Agile")
op("jira_move_to_sprint", "jira", "Move issues to sprint", "jira_move_issues_to_sprint",
   "Add issues (comma separated keys) to a sprint.",
   _f(Field("sprint_id", "Sprint id", kind="number", required=True, default=7),
      Field("issues", "Issues", required=True, placeholder="OPS-42, OPS-43")), "Agile")
op("jira_versions", "jira", "List versions", "jira_list_versions", "Release versions of a project.",
   _f(F_PROJECT_REQ), "Releases")
op("jira_create_version", "jira", "Create version", "jira_create_version", "Plan a release version.",
   _f(F_PROJECT_REQ, Field("name", "Version name", required=True, placeholder="1.5.0"), F_DESC,
      Field("release_date", "Release date", kind="date", placeholder="2026-12-01")), "Releases")
op("jira_myself", "jira", "Who am I", "jira_get_myself", "The authenticated Jira user.", (), "Account")

# =========================================================================== #
# WHATSAPP
# =========================================================================== #
op("wa_send_text", "whatsapp", "Send text", "wa_send_text",
   "Plain text message with optional link preview.",
   _f(F_WA_TO, Field("body", "Message", kind="textarea", required=True, placeholder="Deploy finished - all green ✅"),
      Field("preview_url", "Show link preview", kind="toggle", default=False)), "Send",
   "WhatsApp 919876543210 that the deploy is green")
op("wa_send_template", "whatsapp", "Send template", "wa_send_template",
   "Pre-approved template - required to message someone outside the 24h window.",
   _f(F_WA_TO, Field("template_name", "Template name", required=True, placeholder="appointment_reminder"),
      Field("language_code", "Language", default="en_US", placeholder="en_US"),
      Field("components_json", "Components (JSON)", kind="json",
            placeholder='[{"type":"body","parameters":[{"type":"text","text":"Ada"}]}]')), "Send")
op("wa_send_image", "whatsapp", "Send image", "wa_send_image", "Image from a public URL or media id.",
   _f(F_WA_TO, Field("image_url", "Image URL / media id", required=True, placeholder="https://…/chart.png"),
      Field("caption", "Caption", kind="textarea")), "Media")
op("wa_send_document", "whatsapp", "Send document", "wa_send_document", "PDF, invoice, spreadsheet…",
   _f(F_WA_TO, Field("document_url", "Document URL / media id", required=True, placeholder="https://…/q4.pdf"),
      Field("caption", "Caption"), Field("filename", "Filename", placeholder="q4-report.pdf")), "Media")
op("wa_send_audio", "whatsapp", "Send audio", "wa_send_audio", "Voice note or audio clip.",
   _f(F_WA_TO, Field("audio_url", "Audio URL / media id", required=True, placeholder="https://…/note.mp3")), "Media")
op("wa_send_video", "whatsapp", "Send video", "wa_send_video", "Video from a public URL or media id.",
   _f(F_WA_TO, Field("video_url", "Video URL / media id", required=True), Field("caption", "Caption")), "Media")
op("wa_send_sticker", "whatsapp", "Send sticker", "wa_send_sticker", "WEBP sticker.",
   _f(F_WA_TO, Field("sticker_url", "Sticker URL / media id", required=True)), "Media")
op("wa_send_location", "whatsapp", "Send location", "wa_send_location", "Drop a map pin.",
   _f(F_WA_TO, Field("latitude", "Latitude", kind="number", required=True, default=19.076),
      Field("longitude", "Longitude", kind="number", required=True, default=72.8777),
      Field("name", "Place name"), Field("address", "Address")), "Rich")
op("wa_send_contact", "whatsapp", "Send contact card", "wa_send_contact_card",
   "Share one or more contacts as vCards.",
   _f(F_WA_TO, Field("contact_json", "Contact (JSON)", kind="json", required=True,
                     placeholder='[{"name":{"formatted":"Ada Lovelace","first_name":"Ada"},"phones":[{"phone":"+919876543210","type":"CELL"}]}]')),
   "Rich")
op("wa_send_buttons", "whatsapp", "Send reply buttons", "wa_send_buttons",
   "Up to 3 tappable buttons - perfect for approvals.",
   _f(F_WA_TO, F_WA_TEXT, F_WA_BUTTONS, Field("header_text", "Header"), Field("footer_text", "Footer")), "Rich",
   "Ask Ada to approve the release with Yes / No buttons")
op("wa_send_list", "whatsapp", "Send list menu", "wa_send_list",
   "A picker with up to 10 rows - good for choosing a slot or an option.",
   _f(F_WA_TO, F_WA_TEXT, Field("button_text", "Button label", required=True, default="Choose", placeholder="Pick a slot"),
      F_WA_SECTIONS, Field("header_text", "Header"), Field("footer_text", "Footer")), "Rich")
op("wa_send_cta", "whatsapp", "Send link button", "wa_send_cta_button", "One call-to-action URL button.",
   _f(F_WA_TO, F_WA_TEXT, Field("button_text", "Button label", required=True, default="Open"),
      Field("url", "URL", required=True), Field("header_text", "Header"), Field("footer_text", "Footer")), "Rich")
op("wa_send_reaction", "whatsapp", "React to a message", "wa_send_reaction", "Emoji reaction.",
   _f(F_WA_TO, Field("message_id", "Message id", required=True, placeholder="wamid.HBg…"),
      Field("emoji", "Emoji", kind="select", default="👍",
            options=("👍", "❤️", "😂", "😮", "😢", "🙏", "🔥", "🎉", "✅", "❌"))), "Rich")
op("wa_mark_read", "whatsapp", "Mark as read", "wa_mark_read", "Send the blue-tick read receipt.",
   _f(Field("message_id", "Message id", required=True, placeholder="wamid.HBg…")), "Inbox")
op("wa_get_media", "whatsapp", "Download media", "wa_get_media", "Resolve a media id and save the file.",
   _f(Field("media_id", "Media id", required=True),
      Field("save_path", "Save to", kind="file", placeholder="downloads/invoice.pdf")), "Media")
op("wa_upload_media", "whatsapp", "Upload media", "wa_upload_media",
   "Upload a local file and get the media id to send.",
   _f(F_FILE), "Media")
op("wa_list_templates", "whatsapp", "List templates", "wa_list_templates", "Templates and their review status.",
   _f(Field("limit", "Limit", kind="number", default=50, options=(10, 25, 50, 100))), "Account")
op("wa_create_template", "whatsapp", "Create template", "wa_create_template",
   "Submit a new template for Meta review.",
   _f(Field("name", "Name", required=True, placeholder="daily_digest"),
      Field("body_text", "Body", kind="textarea", required=True, placeholder="Your digest: {{1}}"),
      Field("category", "Category", kind="select", default="UTILITY",
            options=("UTILITY", "MARKETING", "AUTHENTICATION")),
      Field("language_code", "Language", kind="select", default="en_US",
            options=("en_US", "en_GB", "es_ES", "pt_BR", "hi_IN", "fr_FR", "de_DE", "ar_SA")),
      Field("header_text", "Header")), "Account")
op("wa_delete_template", "whatsapp", "Delete template", "wa_delete_template", "Remove a template.",
   _f(Field("name", "Name", required=True)), "Account")
op("wa_business_profile", "whatsapp", "Business profile", "wa_get_business_profile",
   "Read the public profile.", (), "Account")
op("wa_update_profile", "whatsapp", "Update profile", "wa_update_business_profile",
   "Change about/address/website and more.",
   _f(Field("about", "About", placeholder="We reply in minutes"), Field("address", "Address"),
      Field("description", "Description", kind="textarea"), Field("email", "Email"),
      Field("website", "Website", placeholder="https://example.com"),
      Field("vertical", "Vertical", kind="select", default="OTHER",
            options=("OTHER", "AUTO", "BEAUTY", "APPAREL", "EDU", "ENTERTAIN", "EVENT_PLAN", "FINANCE", "GROCERY",
                     "GOVT", "HOTEL", "HEALTH", "NONPROFIT", "PROF_SERVICES", "RETAIL", "TRAVEL", "RESTAURANT")),
      Field("profile_picture_url", "Profile picture URL")), "Account")
op("wa_phone_numbers", "whatsapp", "Phone numbers", "wa_list_phone_numbers", "Numbers on the business account.",
   (), "Account")


# --------------------------------------------------------------------------- #
# form visibility
# --------------------------------------------------------------------------- #
# Fields that are deliberately not rendered in the front-end form. Each hidden
# field is filled with a default at submit time (see HIDDEN_FIELD_DEFAULTS), so
# the underlying tool still receives every parameter it expects.
#
# To put the Calendar picker back on screen, empty this set (and drop the entry
# from HIDDEN_FIELD_DEFAULTS). Nothing else has to change.
HIDDEN_FORM_FIELDS: frozenset[str] = frozenset({"calendar_id"})
HIDDEN_FIELD_DEFAULTS: dict[str, Any] = {"calendar_id": "primary"}


def visible_fields(operation: Operation) -> list[Field]:
    """The fields the UI should render for an operation."""
    return [f for f in operation.fields if f.name not in HIDDEN_FORM_FIELDS]


def hidden_defaults(operation: Operation) -> dict[str, Any]:
    """Values to inject for hidden fields the operation actually accepts."""
    names = {f.name for f in operation.fields}
    return {k: v for k, v in HIDDEN_FIELD_DEFAULTS.items() if k in names}


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #
OPERATION_INDEX: dict[str, Operation] = {o.id: o for o in OPERATIONS}
OPS_BY_APP: dict[str, list[Operation]] = {}
for _o in OPERATIONS:
    OPS_BY_APP.setdefault(_o.app, []).append(_o)


def get_operation(op_id: str) -> Operation | None:
    return OPERATION_INDEX.get(op_id)


def find_by_tool(tool_name: str) -> Operation | None:
    return next((o for o in OPERATIONS if o.tool == tool_name), None)


def groups_for(app: str) -> list[str]:
    seen: list[str] = []
    for operation in OPS_BY_APP.get(app, []):
        if operation.group not in seen:
            seen.append(operation.group)
    return seen


def describe(operation: Operation) -> str:
    parts = [f"**{operation.name}** — {operation.summary}"]
    if operation.required_fields:
        parts.append("Needs: " + ", ".join(f"`{f.label}`" for f in operation.required_fields))
    if operation.example:
        parts.append(f"Try: “{operation.example}”")
    return "  \n".join(parts)
