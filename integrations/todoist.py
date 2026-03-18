from __future__ import annotations
"""Todoist REST API v1 integration (async via httpx)."""

import httpx
import structlog
from datetime import date, timezone, datetime
from typing import Optional

from config.settings import settings

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.todoist.com/api/v1"

_PRIORITY_MAP = {4: "high", 3: "high", 2: "medium", 1: "low"}
_PRIORITY_REVERSE = {"high": 4, "medium": 2, "low": 1}


def _make_headers() -> dict:
    return {"Authorization": f"Bearer {settings.todoist.api_token}"}


def _map_task(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "content": raw["content"],
        "description": raw.get("description", ""),
        "priority": _PRIORITY_MAP.get(raw.get("priority", 1), "low"),
        "due": raw.get("due"),
        "labels": raw.get("labels", []),
        "project_id": raw.get("project_id"),
    }


async def _get_all_pages(url: str, params: Optional[dict] = None) -> list[dict]:
    """Fetch all pages from a paginated v1 endpoint."""
    items = []
    cursor = None
    async with httpx.AsyncClient() as client:
        while True:
            p = dict(params or {})
            if cursor:
                p["cursor"] = cursor
            resp = await client.get(url, headers=_make_headers(), params=p, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("results", []))
            cursor = data.get("next_cursor")
            if not cursor:
                break
    return items


async def get_tasks() -> list[dict]:
    """Return all active tasks."""
    raw = await _get_all_pages(f"{BASE_URL}/tasks")
    tasks = [_map_task(t) for t in raw if not t.get("checked") and not t.get("is_deleted")]
    logger.info("todoist_tasks_fetched", count=len(tasks))
    return tasks


async def get_today_tasks() -> list[dict]:
    """Return tasks due today or overdue, filtered client-side."""
    today_str = date.today().isoformat()
    all_tasks = await get_tasks()
    result = []
    for t in all_tasks:
        due = t.get("due")
        if not due:
            continue
        # due.date is "YYYY-MM-DDTHH:MM:SSZ" or "YYYY-MM-DD"
        due_date = (due.get("date") or "")[:10]
        if due_date and due_date <= today_str:
            result.append(t)
    logger.info("todoist_today_tasks", count=len(result))
    return result


async def add_task(
    content: str,
    priority: str = "medium",
    due_string: Optional[str] = None,
    labels: Optional[list[str]] = None,
    description: Optional[str] = None,
    duration: int = 30,
    duration_unit: str = "minute",
) -> dict:
    """Add a new task and return the created task. Duration defaults to 30 minutes."""
    payload: dict = {
        "content": content,
        "priority": _PRIORITY_REVERSE.get(priority, 2),
        "duration": {"amount": duration, "unit": duration_unit},
    }
    if due_string:
        payload["due_string"] = due_string
    if labels:
        payload["labels"] = labels
    if description:
        payload["description"] = description

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/tasks",
            headers=_make_headers(),
            json=payload,
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.error("todoist_add_task_failed", status=resp.status_code, body=resp.text, payload=payload)
        resp.raise_for_status()

    task = _map_task(resp.json())
    logger.info("todoist_task_added", content=content)
    return task


async def complete_task(task_id: str) -> bool:
    """Mark a task as complete."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/tasks/{task_id}/close",
            headers=_make_headers(),
            timeout=15,
        )
        resp.raise_for_status()
    logger.info("todoist_task_completed", task_id=task_id)
    return True


async def delete_task(task_id: str) -> bool:
    """Delete a task."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{BASE_URL}/tasks/{task_id}",
            headers=_make_headers(),
            timeout=15,
        )
        resp.raise_for_status()
    logger.info("todoist_task_deleted", task_id=task_id)
    return True


async def update_task(task_id: str, **updates) -> dict:
    """Update task properties (content, priority, due_string, due_datetime, duration, etc.)."""
    if "priority" in updates:
        updates["priority"] = _PRIORITY_REVERSE.get(updates["priority"], 2)

    # Todoist v1 wraps duration as {"amount": N, "unit": "minute"}
    if "duration" in updates:
        updates["duration"] = {
            "amount": updates.pop("duration"),
            "unit": updates.pop("duration_unit", "minute"),
        }
    elif "duration_unit" in updates:
        updates.pop("duration_unit")  # avoid sending unit without amount

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/tasks/{task_id}",
            headers=_make_headers(),
            json=updates,
            timeout=15,
        )
        resp.raise_for_status()

    task = _map_task(resp.json())
    logger.info("todoist_task_updated", task_id=task_id)
    return task


async def find_task_by_name(name: str) -> Optional[dict]:
    """Find the first task whose content fuzzy-matches `name`."""
    tasks = await get_tasks()
    name_lower = name.lower().strip()
    for t in tasks:
        if t["content"].lower().strip() == name_lower:
            return t
    for t in tasks:
        if name_lower in t["content"].lower():
            return t
    return None
