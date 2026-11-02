"""Jira tools - issues, transitions, comments, sprints, worklogs, attachments."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

import config
from ._utils import err, jira_request, ok, plain_text, simulated, split_csv
from ._utils import adf as to_adf

APP = "jira"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _issue_card(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields", {}) or {}
    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": fields.get("summary"),
        "type": (fields.get("issuetype") or {}).get("name"),
        "status": (fields.get("status") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "reporter": (fields.get("reporter") or {}).get("displayName"),
        "labels": fields.get("labels", []),
        "due": fields.get("duedate"),
        "updated": fields.get("updated"),
        "url": f"{config.JIRA_BASE_URL}/browse/{issue.get('key')}" if config.JIRA_BASE_URL else "",
    }


def _account_id(user: str) -> str | None:
    """Resolve an email / display name to a Jira accountId."""
    value = (user or "").strip()
    if not value:
        return None
    if " " not in value and "@" not in value and ":" not in value:
        return value  # already an accountId
    try:
        found = jira_request("GET", "api/3/user/search", params={"query": value, "maxResults": 1})
        if found:
            return found[0].get("accountId")
    except Exception:
        pass
    return None


def _search_fields(fields: str) -> list[str]:
    return split_csv(fields) or ["summary", "status", "assignee", "issuetype", "priority", "labels", "duedate", "updated"]


# --------------------------------------------------------------------------- #
# identity / discovery
# --------------------------------------------------------------------------- #
@tool
def jira_get_myself() -> str:
    """Return the authenticated Jira user (name, email, timezone)."""
    if config.simulating(APP):
        return simulated(APP, "get_myself", displayName="You", emailAddress="you@example.com")
    try:
        me = jira_request("GET", "api/3/myself")
        return ok(user={k: me.get(k) for k in ("accountId", "displayName", "emailAddress", "timeZone", "active")})
    except Exception as exc:
        return err(f"get_myself failed: {exc}")


@tool
def jira_list_projects(limit: int = 50) -> str:
    """List Jira projects the user can see (key, name, type)."""
    if config.simulating(APP):
        return simulated(APP, "list_projects", projects=[{"key": "OPS", "name": "Operations"}, {"key": "ENG", "name": "Engineering"}])
    try:
        projects = jira_request("GET", "api/3/project", params={"maxResults": max(1, min(int(limit), 100))})
        return ok(count=len(projects), projects=[
            {"key": p.get("key"), "name": p.get("name"), "type": p.get("projectTypeKey"), "id": p.get("id")}
            for p in projects
        ])
    except Exception as exc:
        return err(f"list_projects failed: {exc}")


@tool
def jira_get_project(project_key: str) -> str:
    """Show one project plus every issue type you can create and all workflow statuses."""
    if config.simulating(APP):
        return simulated(APP, "get_project", key=project_key,
                         issue_types=["Task", "Bug", "Story", "Epic"], statuses=["To Do", "In Progress", "Done"])
    try:
        project = jira_request("GET", f"api/3/project/{project_key}")
        statuses = sorted({s.get("name") for t in project.get("issueTypes", [])
                           for s in (t.get("statuses") or []) if s.get("name")})
        return ok(
            key=project.get("key"),
            name=project.get("name"),
            lead=(project.get("lead") or {}).get("displayName"),
            issue_types=[t.get("name") for t in project.get("issueTypes", [])],
            statuses=statuses,
        )
    except Exception as exc:
        return err(f"get_project failed: {exc}")


@tool
def jira_list_users(query: str, limit: int = 10) -> str:
    """Search users by name or email (useful before assigning an issue)."""
    if config.simulating(APP):
        return simulated(APP, "list_users", users=[{"accountId": "sim-acc-1", "displayName": "Ada Lovelace", "emailAddress": "ada@example.com"}])
    try:
        users = jira_request("GET", "api/3/user/search", params={"query": query, "maxResults": max(1, min(int(limit), 50))})
        return ok(count=len(users), users=[
            {"accountId": u.get("accountId"), "displayName": u.get("displayName"), "emailAddress": u.get("emailAddress")}
            for u in users
        ])
    except Exception as exc:
        return err(f"list_users failed: {exc}")


# --------------------------------------------------------------------------- #
# issues
# --------------------------------------------------------------------------- #
@tool
def jira_get_issue(issue_key: str) -> str:
    """Fetch a single issue with description, comments count, assignee and status."""
    if config.simulating(APP):
        return simulated(APP, "get_issue", key=issue_key, summary="Checkout latency spike", status="In Progress")
    try:
        issue = jira_request("GET", f"api/3/issue/{issue_key}")
        fields = issue.get("fields", {})
        return ok(issue={**_issue_card(issue), "description": plain_text(fields.get("description"))[:8000],
                         "comments": (fields.get("comment") or {}).get("total", 0),
                         "created": fields.get("created"), "parent": (fields.get("parent") or {}).get("key")})
    except Exception as exc:
        return err(f"get_issue failed: {exc}")


@tool
def jira_create_issue(
    summary: str,
    project_key: str = "",
    issue_type: str = "",
    description: str = "",
    assignee: str = "",
    priority: str = "",
    labels: str = "",
    due_date: str = "",
    parent_key: str = "",
) -> str:
    """Create an issue. Labels are comma separated, due_date is YYYY-MM-DD, parent_key links a subtask to its parent."""
    if config.simulating(APP):
        return simulated(APP, "create_issue", key="OPS-101", summary=summary, project=project_key or config.JIRA_DEFAULT_PROJECT)
    try:
        project = project_key or config.JIRA_DEFAULT_PROJECT
        if not project:
            return err("project_key is required (or set JIRA_DEFAULT_PROJECT in .env).")
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type or config.JIRA_ISSUE_TYPE},
        }
        if description:
            fields["description"] = to_adf(description)
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = split_csv(labels)
        if due_date:
            fields["duedate"] = due_date
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if assignee:
            account = _account_id(assignee)
            if not account:
                return err(f"Could not resolve assignee '{assignee}' to a Jira accountId. Use jira_list_users first.")
            fields["assignee"] = {"accountId": account}
        created = jira_request("POST", "api/3/issue", json={"fields": fields})
        return ok(key=created.get("key"), id=created.get("id"),
                  url=f"{config.JIRA_BASE_URL}/browse/{created.get('key')}", project=project)
    except Exception as exc:
        return err(f"create_issue failed: {exc}")


@tool
def jira_update_issue(
    issue_key: str,
    summary: str = "",
    description: str = "",
    assignee: str = "",
    priority: str = "",
    labels: str = "",
    due_date: str = "",
    issue_type: str = "",
) -> str:
    """Update fields on an existing issue. Only the fields you pass are changed."""
    if config.simulating(APP):
        return simulated(APP, "update_issue", key=issue_key, summary=summary or None)
    try:
        fields: dict[str, Any] = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = to_adf(description)
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = split_csv(labels)
        if due_date:
            fields["duedate"] = due_date
        if issue_type:
            fields["issuetype"] = {"name": issue_type}
        if assignee:
            account = _account_id(assignee)
            if not account:
                return err(f"Could not resolve assignee '{assignee}'.")
            fields["assignee"] = {"accountId": account}
        if not fields:
            return err("Nothing to update - pass at least one field.")
        jira_request("PUT", f"api/3/issue/{issue_key}", json={"fields": fields})
        return ok(updated=issue_key, changed=list(fields))
    except Exception as exc:
        return err(f"update_issue failed: {exc}")


@tool
def jira_assign_issue(issue_key: str, assignee: str) -> str:
    """Assign an issue to a user (email, display name or accountId)."""
    if config.simulating(APP):
        return simulated(APP, "assign_issue", key=issue_key, assignee=assignee)
    try:
        account = _account_id(assignee)
        if not account:
            return err(f"Could not resolve '{assignee}' to a Jira accountId.")
        jira_request("PUT", f"api/3/issue/{issue_key}/assignee", json={"accountId": account})
        return ok(assigned=issue_key, account_id=account)
    except Exception as exc:
        return err(f"assign_issue failed: {exc}")


@tool
def jira_delete_issue(issue_key: str, delete_subtasks: bool = False) -> str:
    """Permanently delete an issue. Set delete_subtasks=True to cascade."""
    if config.simulating(APP):
        return simulated(APP, "delete_issue", key=issue_key)
    try:
        jira_request("DELETE", f"api/3/issue/{issue_key}", params={"deleteSubtasks": str(bool(delete_subtasks)).lower()})
        return ok(deleted=issue_key)
    except Exception as exc:
        return err(f"delete_issue failed: {exc}")


@tool
def jira_search(jql: str, max_results: int = 20, fields: str = "") -> str:
    """Run a JQL query, e.g. "project = OPS AND status != Done ORDER BY updated DESC". `fields` is a comma separated field list."""
    if config.simulating(APP):
        return simulated(APP, "search", jql=jql, issues=[{"key": "OPS-42", "summary": "Latency spike", "status": "In Progress"}])
    payload = {"jql": jql, "maxResults": max(1, min(int(max_results), 100)), "fields": _search_fields(fields)}
    try:
        data = jira_request("POST", "api/3/search/jql", json=payload)
    except Exception:
        try:
            data = jira_request("GET", "api/3/search", params=payload)
        except Exception as exc:
            return err(f"search failed: {exc}")
    issues = [_issue_card(i) for i in data.get("issues", [])]
    return ok(jql=jql, count=len(issues), total=data.get("total"), issues=issues)


# --------------------------------------------------------------------------- #
# workflow + collaboration
# --------------------------------------------------------------------------- #
@tool
def jira_list_transitions(issue_key: str) -> str:
    """List the workflow transitions currently available for an issue (id + target status)."""
    if config.simulating(APP):
        return simulated(APP, "list_transitions", transitions=[{"id": "31", "name": "Start Progress", "to": "In Progress"}])
    try:
        data = jira_request("GET", f"api/3/issue/{issue_key}/transitions")
        return ok(issue=issue_key, transitions=[
            {"id": t.get("id"), "name": t.get("name"), "to": (t.get("to") or {}).get("name")}
            for t in data.get("transitions", [])
        ])
    except Exception as exc:
        return err(f"list_transitions failed: {exc}")


@tool
def jira_transition_issue(issue_key: str, transition: str, comment: str = "") -> str:
    """Move an issue to another status. `transition` can be the transition name ('In Progress') or its id."""
    if config.simulating(APP):
        return simulated(APP, "transition_issue", key=issue_key, transition=transition)
    try:
        available = jira_request("GET", f"api/3/issue/{issue_key}/transitions").get("transitions", [])
        wanted = transition.strip().lower()
        match = next((t for t in available if str(t.get("id")) == wanted), None) or next(
            (t for t in available if t.get("name", "").lower() == wanted), None
        ) or next((t for t in available if wanted in t.get("name", "").lower()
                   or wanted == (t.get("to") or {}).get("name", "").lower()), None)
        if not match:
            options = [f"{t.get('id')}={t.get('name')}->{(t.get('to') or {}).get('name')}" for t in available]
            return err(f"Transition '{transition}' not available. Options: {', '.join(options) or 'none'}")
        body: dict[str, Any] = {"transition": {"id": match.get("id")}}
        if comment:
            body["update"] = {"comment": [{"add": {"body": to_adf(comment)}}]}
        jira_request("POST", f"api/3/issue/{issue_key}/transitions", json=body)
        return ok(issue=issue_key, moved_to=(match.get("to") or {}).get("name"), transition=match.get("name"))
    except Exception as exc:
        return err(f"transition_issue failed: {exc}")


@tool
def jira_add_comment(issue_key: str, comment: str) -> str:
    """Add a comment to an issue."""
    if config.simulating(APP):
        return simulated(APP, "add_comment", key=issue_key, comment=comment[:120])
    try:
        created = jira_request("POST", f"api/3/issue/{issue_key}/comment", json={"body": to_adf(comment)})
        return ok(issue=issue_key, comment_id=created.get("id"), created=created.get("created"))
    except Exception as exc:
        return err(f"add_comment failed: {exc}")


@tool
def jira_get_comments(issue_key: str, max_results: int = 20) -> str:
    """Read the comments on an issue."""
    if config.simulating(APP):
        return simulated(APP, "get_comments", comments=[{"author": "Ada", "body": "Taking a look now."}])
    try:
        data = jira_request("GET", f"api/3/issue/{issue_key}/comment", params={"maxResults": max(1, min(int(max_results), 100))})
        return ok(issue=issue_key, total=data.get("total"), comments=[
            {"id": c.get("id"), "author": (c.get("author") or {}).get("displayName"),
             "created": c.get("created"), "body": plain_text(c.get("body"))[:4000]}
            for c in data.get("comments", [])
        ])
    except Exception as exc:
        return err(f"get_comments failed: {exc}")


@tool
def jira_update_comment(issue_key: str, comment_id: str, comment: str) -> str:
    """Edit one of your comments."""
    if config.simulating(APP):
        return simulated(APP, "update_comment", key=issue_key, comment_id=comment_id)
    try:
        jira_request("PUT", f"api/3/issue/{issue_key}/comment/{comment_id}", json={"body": to_adf(comment)})
        return ok(updated_comment=comment_id, issue=issue_key)
    except Exception as exc:
        return err(f"update_comment failed: {exc}")


@tool
def jira_delete_comment(issue_key: str, comment_id: str) -> str:
    """Delete a comment."""
    if config.simulating(APP):
        return simulated(APP, "delete_comment", key=issue_key, comment_id=comment_id)
    try:
        jira_request("DELETE", f"api/3/issue/{issue_key}/comment/{comment_id}")
        return ok(deleted_comment=comment_id, issue=issue_key)
    except Exception as exc:
        return err(f"delete_comment failed: {exc}")


@tool
def jira_add_attachment(issue_key: str, file_path: str) -> str:
    """Attach a local file to an issue."""
    if config.simulating(APP):
        return simulated(APP, "add_attachment", key=issue_key, file=file_path)
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return err(f"File not found: {path}")
        with path.open("rb") as handle:
            data = jira_request(
                "POST", f"api/3/issue/{issue_key}/attachments",
                files={"file": (path.name, handle, mimetypes.guess_type(path.name)[0] or "application/octet-stream")},
                headers={"X-Atlassian-Token": "no-check"},
            )
        return ok(issue=issue_key, attachments=[{"id": a.get("id"), "filename": a.get("filename")} for a in data])
    except Exception as exc:
        return err(f"add_attachment failed: {exc}")


@tool
def jira_add_worklog(issue_key: str, time_spent: str, comment: str = "", started: str = "") -> str:
    """Log work on an issue. `time_spent` uses Jira syntax: '2h 30m', '1d'. `started` is ISO-8601."""
    if config.simulating(APP):
        return simulated(APP, "add_worklog", key=issue_key, time_spent=time_spent)
    try:
        body: dict[str, Any] = {"timeSpent": time_spent}
        if comment:
            body["comment"] = to_adf(comment)
        if started:
            body["started"] = started
        log = jira_request("POST", f"api/3/issue/{issue_key}/worklog", json=body)
        return ok(issue=issue_key, worklog_id=log.get("id"), time_spent=log.get("timeSpent"))
    except Exception as exc:
        return err(f"add_worklog failed: {exc}")


@tool
def jira_link_issues(outward_issue: str, inward_issue: str, link_type: str = "Blocks", comment: str = "") -> str:
    """Link two issues, e.g. outward_issue 'OPS-1' Blocks inward_issue 'OPS-2'."""
    if config.simulating(APP):
        return simulated(APP, "link_issues", outward=outward_issue, inward=inward_issue, link_type=link_type)
    try:
        body: dict[str, Any] = {
            "type": {"name": link_type},
            "outwardIssue": {"key": outward_issue},
            "inwardIssue": {"key": inward_issue},
        }
        if comment:
            body["comment"] = {"body": to_adf(comment)}
        jira_request("POST", "api/3/issueLink", json=body)
        return ok(linked=f"{outward_issue} {link_type} {inward_issue}")
    except Exception as exc:
        return err(f"link_issues failed: {exc}")


@tool
def jira_add_watcher(issue_key: str, user: str) -> str:
    """Add someone as a watcher on an issue."""
    if config.simulating(APP):
        return simulated(APP, "add_watcher", key=issue_key, user=user)
    try:
        account = _account_id(user)
        if not account:
            return err(f"Could not resolve '{user}'.")
        jira_request("POST", f"api/3/issue/{issue_key}/watchers", data=json.dumps(account),
                     headers={"Content-Type": "application/json"})
        return ok(issue=issue_key, watching=True, account_id=account)
    except Exception as exc:
        return err(f"add_watcher failed: {exc}")


@tool
def jira_remove_watcher(issue_key: str, account_id: str) -> str:
    """Remove a watcher by accountId."""
    if config.simulating(APP):
        return simulated(APP, "remove_watcher", key=issue_key, account_id=account_id)
    try:
        jira_request("DELETE", f"api/3/issue/{issue_key}/watchers", params={"accountId": account_id})
        return ok(issue=issue_key, watching=False, account_id=account_id)
    except Exception as exc:
        return err(f"remove_watcher failed: {exc}")


# --------------------------------------------------------------------------- #
# agile / sprints / versions
# --------------------------------------------------------------------------- #
@tool
def jira_list_boards(limit: int = 20) -> str:
    """List agile boards (id, name, type)."""
    if config.simulating(APP):
        return simulated(APP, "list_boards", boards=[{"id": 1, "name": "OPS board", "type": "scrum"}])
    try:
        data = jira_request("GET", "agile/1.0/board", params={"maxResults": max(1, min(int(limit), 50))})
        return ok(boards=[{"id": b.get("id"), "name": b.get("name"), "type": b.get("type")} for b in data.get("values", [])])
    except Exception as exc:
        return err(f"list_boards failed: {exc}")


@tool
def jira_list_sprints(board_id: int, state: str = "active,future") -> str:
    """List sprints on a board. state can be active,future,closed."""
    if config.simulating(APP):
        return simulated(APP, "list_sprints", sprints=[{"id": 7, "name": "Sprint 14", "state": "active"}])
    try:
        data = jira_request("GET", f"agile/1.0/board/{board_id}/sprint", params={"state": state})
        return ok(sprints=[
            {"id": s.get("id"), "name": s.get("name"), "state": s.get("state"),
             "start": s.get("startDate"), "end": s.get("endDate")}
            for s in data.get("values", [])
        ])
    except Exception as exc:
        return err(f"list_sprints failed: {exc}")


@tool
def jira_create_sprint(name: str, board_id: int, start_date: str = "", end_date: str = "", goal: str = "") -> str:
    """Create a sprint on a board."""
    if config.simulating(APP):
        return simulated(APP, "create_sprint", id=8, name=name, board_id=board_id)
    try:
        body: dict[str, Any] = {"name": name, "originBoardId": int(board_id)}
        if start_date:
            body["startDate"] = start_date
        if end_date:
            body["endDate"] = end_date
        if goal:
            body["goal"] = goal
        sprint = jira_request("POST", "agile/1.0/sprint", json=body)
        return ok(id=sprint.get("id"), name=sprint.get("name"), state=sprint.get("state"))
    except Exception as exc:
        return err(f"create_sprint failed: {exc}")


@tool
def jira_sprint_issues(sprint_id: int, max_results: int = 50) -> str:
    """List the issues inside a sprint."""
    if config.simulating(APP):
        return simulated(APP, "sprint_issues", issues=[{"key": "OPS-42", "summary": "Latency spike"}])
    try:
        data = jira_request("GET", f"agile/1.0/sprint/{sprint_id}/issue",
                            params={"maxResults": max(1, min(int(max_results), 100))})
        return ok(count=len(data.get("issues", [])), issues=[_issue_card(i) for i in data.get("issues", [])])
    except Exception as exc:
        return err(f"sprint_issues failed: {exc}")


@tool
def jira_move_issues_to_sprint(sprint_id: int, issues: str) -> str:
    """Move one or more issues (comma separated keys) into a sprint."""
    if config.simulating(APP):
        return simulated(APP, "move_to_sprint", sprint_id=sprint_id, issues=split_csv(issues))
    try:
        keys = split_csv(issues)
        jira_request("POST", f"agile/1.0/sprint/{sprint_id}/issue", json={"issues": keys})
        return ok(sprint_id=sprint_id, moved=keys)
    except Exception as exc:
        return err(f"move_issues_to_sprint failed: {exc}")


@tool
def jira_list_versions(project_key: str) -> str:
    """List release versions of a project."""
    if config.simulating(APP):
        return simulated(APP, "list_versions", versions=[{"id": "10000", "name": "1.4.0", "released": False}])
    try:
        versions = jira_request("GET", f"api/3/project/{project_key}/versions")
        return ok(versions=[
            {"id": v.get("id"), "name": v.get("name"), "released": v.get("released"),
             "releaseDate": v.get("releaseDate"), "description": v.get("description")}
            for v in versions
        ])
    except Exception as exc:
        return err(f"list_versions failed: {exc}")


@tool
def jira_create_version(project_key: str, name: str, description: str = "", release_date: str = "") -> str:
    """Create a release version (release_date is YYYY-MM-DD)."""
    if config.simulating(APP):
        return simulated(APP, "create_version", id="10001", name=name, project=project_key)
    try:
        body: dict[str, Any] = {"project": project_key, "name": name, "released": False}
        if description:
            body["description"] = description
        if release_date:
            body["releaseDate"] = release_date
        version = jira_request("POST", "api/3/version", json=body)
        return ok(id=version.get("id"), name=version.get("name"), release_date=version.get("releaseDate"))
    except Exception as exc:
        return err(f"create_version failed: {exc}")


JIRA_TOOLS = [
    jira_get_myself,
    jira_list_projects,
    jira_get_project,
    jira_list_users,
    jira_get_issue,
    jira_create_issue,
    jira_update_issue,
    jira_assign_issue,
    jira_delete_issue,
    jira_search,
    jira_list_transitions,
    jira_transition_issue,
    jira_add_comment,
    jira_get_comments,
    jira_update_comment,
    jira_delete_comment,
    jira_add_attachment,
    jira_add_worklog,
    jira_link_issues,
    jira_add_watcher,
    jira_remove_watcher,
    jira_list_boards,
    jira_list_sprints,
    jira_create_sprint,
    jira_sprint_issues,
    jira_move_issues_to_sprint,
    jira_list_versions,
    jira_create_version,
]
