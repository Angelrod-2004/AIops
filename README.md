# ◈ Nexus Ops Grid

A **multi-agent AI control surface** built with **LangGraph** + **Streamlit** that performs real operations on
**Gmail**, **Google Calendar**, **Jira** and **WhatsApp** — 94 operations, one supervisor, four specialist agents.

Pick an app → pick an operation → fill the fields → **Execute**. The graph fans the work out to the right
specialist agent(s) *in parallel* and reports back with a full tool-call trace. Or skip the forms entirely and
describe the outcome in plain English.

```
                                   ┌──────────────────────────┐
   you ──────────────────────────▶ │  Supervisor (LangGraph)  │
   · Command Deck form            │  plan → route via Send() │
   · one sentence of English      └────────────┬─────────────┘
                                               │  parallel superstep
        ┌────────────────┬─────────────────────┼─────────────────────┐
        ▼                ▼                     ▼                     ▼
   ✉ Gmail agent   ◷ Calendar agent      ◆ Jira agent        ◉ WhatsApp agent
   25 tools        19 tools              28 tools            22 tools
        └────────────────┴─────────────────────┴─────────────────────┘
                                               ▼
                                   report + per-call trace
```

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env            # optional — everything works without it in simulated mode
streamlit run app.py
```

Then open <http://localhost:8501>.

Windows shortcut: double-click **`run.bat`**.

> **No credentials? No problem.** Any app without keys automatically runs in **SIMULATED** mode: tools return
> realistic fixtures instead of calling the network, so the whole graph, UI and report are testable offline.
> The app cards show `SIMULATED` vs `LIVE` at all times.

---

## Two ways to drive it

### 1 · Command Deck (deterministic, no LLM)
Choose an app (✉ / ◷ / ◆ / ◉), choose a group and an operation, fill the fields marked `*`, then
**Add to run queue**. Queue as many actions as you like — across different apps — and press **Execute queue**.
Each queued task maps to exactly one typed tool, so the execution is deterministic and auditable:
tool name, exact arguments and raw API payload are all visible in the report.

Presets queue a ready-made run in one click, including **“All four at once”**, which fires the Gmail, Calendar,
Jira and WhatsApp agents simultaneously to demonstrate the parallel fan-out.

### 2 · Agent Chat (LLM)
Type what you want:

> *“Find a free 30 minute slot with ada@example.com tomorrow afternoon, book it with a Meet link,
> then WhatsApp her the invite.”*

The supervisor turns that into tasks (validated against the operation catalogue), routes each one to its
specialist, and the specialist may chain several tools to finish the job. Chat mode needs one LLM key in `.env`:

```ini
LLM_PROVIDER=openai            # openai | anthropic | google | groq | ollama
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

Any OpenAI-compatible endpoint works via `LLM_BASE_URL` (OpenRouter, Azure, vLLM, LM Studio…).

---

## Connecting the four apps

### Gmail + Google Calendar (one OAuth token covers both)
1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials) create an **OAuth client ID →
   Desktop app**, and enable the **Gmail API** and **Google Calendar API**.
2. Download the JSON to `credentials/google_client_secret.json`.
3. Run the helper — it opens a browser, grants the scopes and writes a refreshable token:

```bash
python scripts/google_auth.py
```

Scopes requested: `gmail.modify`, `gmail.send`, `gmail.labels`, `calendar`.

### Jira Cloud
```ini
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...          # https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_DEFAULT_PROJECT=OPS
```

### WhatsApp Cloud API
```ini
WHATSAPP_TOKEN=EAAG...              # permanent system-user token
WHATSAPP_PHONE_NUMBER_ID=1234567890
WHATSAPP_BUSINESS_ID=0987654321
```

### WhatsApp contacts
The WhatsApp operations have a **Saved WhatsApp contacts** panel above the form (search, Use, Edit, save new).
Press **Use** on a contact and its number is dropped straight into the **To** field of the operation you have open —
it's applied once, so you can still edit it afterwards. Contacts persist in `wa_contacts.json`.

Remember WhatsApp's 24-hour rule: free-form messages are only allowed within 24h of the user's last message —
otherwise use a **template** (`Send template`). The Cloud API is send-first: to *receive* messages you need a
webhook endpoint (this app is an outbound control surface, not a webhook receiver).

---

## What's covered

| App | Ops | Groups |
|---|---:|---|
| ✉ **Gmail** | 25 | Compose · Inbox · Labels · Conversations · Attachments · Account |
| ◷ **Google Calendar** | 19 | Read · Write · Guests · Availability · Calendars · Sharing |
| ◆ **Jira** | 28 | Write · Read · Discover · Agile · Releases · Account |
| ◉ **WhatsApp** | 22 | Send · Media · Rich · Inbox · Account |

Highlights:

- **Gmail** — send / reply / reply-all / forward with attachments, drafts (create, list, send, delete),
  search with Gmail query syntax, read threads, trash/untrash/delete, label management, download attachments.
- **Calendar** — create/update/move/delete events, Google Meet links, recurrence (RRULE), invitations and RSVP,
  quick-add from a sentence, recurring instances, sharing/ACL, and **free-slot finding** that intersects every
  attendee's busy blocks inside working hours.
- **Jira** — create/update/assign/delete issues, JQL search, workflow transitions (by name or id), comments,
  worklogs, issue links, watchers, attachments, boards, sprints (create, list, move issues), versions.
- **WhatsApp** — text, templates, image/document/audio/video/sticker, location, contact cards, reply buttons,
  list menus, CTA-URL buttons, reactions, read receipts, media upload/download, template and profile management.

Dates accept **natural language** everywhere: `tomorrow 3pm`, `next monday 09:30`, `in 2 hours`,
`friday afternoon`, or plain ISO-8601.

---

## Project layout

```
app.py                  Streamlit front-end (Command Deck, Agent Chat, Run Log, How it works)
config.py               env loading, per-app connection status, simulate/live resolution
operations.py           the operation catalogue — drives every form field in the UI
agents/core.py          LLM factory, deterministic tool runner, tool-calling loop, task executor
agents/graph.py         LangGraph: supervisor → parallel Send fan-out → specialists → report
tools/gmail_tools.py    25 @tool functions over the Gmail v1 API
tools/calendar_tools.py 19 @tool functions over the Calendar v3 API + free-slot solver
tools/jira_tools.py     28 @tool functions over Jira REST v3 + Agile 1.0
tools/whatsapp_tools.py 22 @tool functions over the WhatsApp Cloud API
tools/registry.py       tool index (name → tool, app → tools)
ui/theme.py             the futuristic CSS layer (glassmorphism, neon gradients, animated grid)
ui/components.py        hero, app cards, dynamic fields, queue rows, result cards, diagrams
scripts/                google_auth.py · check_catalog.py · selftest.py · smoke_test.py · ui_test.py
```

### Why the operation catalogue matters
`operations.py` is the single source of truth: one `Operation` = one `@tool` + typed `Field`s. The UI builds its
forms, validation and run queue entirely from it, and the chat planner is validated against it. Adding an
operation is a two-step change:

1. Write a `@tool` in the matching `tools/*_tools.py` (and add it to that module's `*_TOOLS` list).
2. Add one `op(...)` entry in `operations.py` whose field names match the tool's parameters.

Then run `python scripts/check_catalog.py` — it fails loudly if the catalogue and tool signatures drift apart.

---

## Verification

```bash
python scripts/check_catalog.py        # 94 operations ↔ 94 tools, signatures aligned
python scripts/audit_fields.py         # no tool parameter is left unsurfaced in the UI
python scripts/selftest.py             # 32 pure-logic checks (dates, payloads, planner validation)
python scripts/smoke_test.py           # runs the real LangGraph fan-out with 5 tasks, incl. a validation failure
python scripts/ui_test.py              # AppTest: presets, execution, form submit, contact "Use" prefill
python scripts/field_coverage_test.py  # every catalog field renders a widget (walks all 94 operations)
```

All test scripts force **simulated** mode, so running them never sends mail, creates events or messages anyone.

---

## Notes on safety

- **Nothing is stored** beyond the session; the Run Log is in-memory and can be exported as JSON.
- Credentials stay in `.env` / `credentials/`, both git-ignored. Secrets are never printed — tool arguments are
  redacted in the trace.
- Destructive operations (permanent delete of mail/threads/issues) are clearly labelled in the UI and still
  require an explicit queue + Execute.
- `SIMULATE_MODE=never` forces live calls and surfaces auth errors instead of hiding them;
  `always` guarantees no network access at all.
