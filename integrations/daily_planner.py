"""Time-boxing daily planner ported from hanzy-ai-assistant."""

from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Default working window
DEFAULT_WORK_START = "07:00"
DEFAULT_WORK_END = "18:00"
DEFAULT_LUNCH_START = "12:00"
DEFAULT_LUNCH_DURATION = 60  # minutes
DEFAULT_TASK_DURATION = 60  # minutes


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _time_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _minutes_to_time(minutes: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def _add_minutes(t: str, delta: int) -> str:
    return _minutes_to_time(_time_to_minutes(t) + delta)


def _blocks_overlap(a: dict, b: dict) -> bool:
    a_start = _time_to_minutes(a["start"])
    a_end = _time_to_minutes(a["end"])
    b_start = _time_to_minutes(b["start"])
    b_end = _time_to_minutes(b["end"])
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Core planner
# ---------------------------------------------------------------------------

def generate_daily_plan(
    todos: list[dict],
    calendar_events: list[dict] | None = None,
    preferences: dict | None = None,
) -> dict:
    """
    Generate a time-boxed daily plan.

    todos: list of {id, content, priority, due, duration (optional)}
    calendar_events: list of {id, title, start, end}
    preferences: override defaults (work_start, work_end, lunch_start, lunch_duration)

    Returns a plan dict with timeblocks.
    """
    prefs = preferences or {}
    work_start = prefs.get("work_start", DEFAULT_WORK_START)
    work_end = prefs.get("work_end", DEFAULT_WORK_END)
    lunch_start = prefs.get("lunch_start", DEFAULT_LUNCH_START)
    lunch_duration = prefs.get("lunch_duration", DEFAULT_LUNCH_DURATION)

    # Build locked blocks: morning routine, lunch, calendar events
    locked_blocks: list[dict] = [
        {
            "id": "morning_routine",
            "title": "Morning routine",
            "start": work_start,
            "end": _add_minutes(work_start, 60),
            "type": "locked",
            "locked": True,
        },
        {
            "id": "lunch",
            "title": "Lunch",
            "start": lunch_start,
            "end": _add_minutes(lunch_start, lunch_duration),
            "type": "locked",
            "locked": True,
        },
    ]

    for event in (calendar_events or []):
        locked_blocks.append({
            "id": event.get("id", str(uuid.uuid4())),
            "title": event.get("title", "Calendar event"),
            "start": event["start"],
            "end": event["end"],
            "type": "calendar",
            "locked": True,
        })

    # Sort locked blocks
    locked_blocks.sort(key=lambda b: _time_to_minutes(b["start"]))

    # Find available slots between locked blocks within work window
    available_slots = _find_available_slots(locked_blocks, work_start, work_end)

    # Sort todos by priority (high → medium → low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_todos = sorted(
        todos,
        key=lambda t: priority_order.get(t.get("priority", "medium"), 1),
    )

    # Assign todos to slots
    task_blocks: list[dict] = []
    pending: list[dict] = []

    for todo in sorted_todos:
        duration = todo.get("duration", DEFAULT_TASK_DURATION)
        slot = _find_best_slot(available_slots, duration, todo.get("priority", "medium"))

        if slot:
            block = {
                "id": todo.get("id", str(uuid.uuid4())),
                "title": todo["content"],
                "start": slot["start"],
                "end": _add_minutes(slot["start"], duration),
                "type": "task",
                "locked": False,
                "completed": False,
                "skipped": False,
                "priority": todo.get("priority", "medium"),
                "todoist_id": todo.get("id"),
                "duration": duration,
            }
            task_blocks.append(block)

            # Shrink or remove the consumed slot
            new_start = _add_minutes(slot["start"], duration)
            if _time_to_minutes(new_start) < _time_to_minutes(slot["end"]):
                slot["start"] = new_start
            else:
                available_slots.remove(slot)
        else:
            pending.append(todo)

    all_blocks = sorted(locked_blocks + task_blocks, key=lambda b: _time_to_minutes(b["start"]))

    total_tasks = len(sorted_todos)
    plan = {
        "date": date.today().isoformat(),
        "timeblocks": all_blocks,
        "pending": pending,
        "total_tasks": total_tasks,
        "completed_tasks": 0,
        "skipped_tasks": 0,
        "completion_rate": 0.0,
    }

    logger.info("daily_plan_generated", total_tasks=total_tasks, pending=len(pending))
    return plan


def rejig_day(
    plan: dict,
    current_time: str,
    strategy: str = "focus",
) -> dict:
    """
    Reorganize remaining tasks from current_time onward.

    strategy: "focus" (high priority first), "quick_wins" (shortest first),
              "aggressive" (push all tasks back-to-back)
    """
    now_minutes = _time_to_minutes(current_time)

    # Gather incomplete tasks that haven't started yet or are still running
    remaining = [
        b for b in plan["timeblocks"]
        if b.get("type") == "task"
        and not b.get("completed")
        and not b.get("skipped")
        and _time_to_minutes(b["end"]) > now_minutes
    ]

    locked = [b for b in plan["timeblocks"] if b.get("locked")]
    work_end = "18:00"

    # Determine available slots from now
    future_locked = [b for b in locked if _time_to_minutes(b["end"]) > now_minutes]
    available = _find_available_slots(future_locked, current_time, work_end)
    available_minutes = sum(
        _time_to_minutes(s["end"]) - _time_to_minutes(s["start"])
        for s in available
    )

    # Sort remaining tasks by strategy
    if strategy == "quick_wins":
        remaining.sort(key=lambda b: b.get("duration", DEFAULT_TASK_DURATION))
    elif strategy == "focus":
        priority_order = {"high": 0, "medium": 1, "low": 2}
        remaining.sort(key=lambda b: priority_order.get(b.get("priority", "medium"), 1))
    # "aggressive" keeps original order

    # Reassign remaining tasks to available slots
    new_blocks = []
    for task in remaining:
        duration = task.get("duration", DEFAULT_TASK_DURATION)
        slot = _find_best_slot(available, duration, task.get("priority", "medium"))
        if slot:
            task = {**task, "start": slot["start"], "end": _add_minutes(slot["start"], duration)}
            new_blocks.append(task)
            new_start = _add_minutes(slot["start"], duration)
            if _time_to_minutes(new_start) < _time_to_minutes(slot["end"]):
                slot["start"] = new_start
            else:
                available.remove(slot)

    # Replace task blocks in plan with rejigged ones
    non_task_blocks = [b for b in plan["timeblocks"] if b.get("locked")]
    completed = [b for b in plan["timeblocks"] if b.get("type") == "task" and b.get("completed")]
    plan["timeblocks"] = sorted(
        non_task_blocks + completed + new_blocks,
        key=lambda b: _time_to_minutes(b["start"]),
    )
    plan["rejig_count"] = plan.get("rejig_count", 0) + 1

    logger.info("day_rejigged", strategy=strategy, remaining_tasks=len(new_blocks))
    return plan


def add_task_to_plan(plan: dict, task: dict, preferred_time: Optional[str] = None) -> tuple[bool, Optional[dict]]:
    """Add a task to the plan. Returns (success, block)."""
    duration = task.get("duration", DEFAULT_TASK_DURATION)
    work_end = "18:00"

    locked = [b for b in plan["timeblocks"] if b.get("locked")]
    now = datetime.now().strftime("%H:%M")
    available = _find_available_slots(locked, preferred_time or now, work_end)

    if not available:
        return False, None

    slot = available[0] if preferred_time else _find_best_slot(available, duration, task.get("priority", "medium"))
    if not slot:
        return False, None

    block = {
        "id": task.get("id", str(uuid.uuid4())),
        "title": task["content"],
        "start": slot["start"],
        "end": _add_minutes(slot["start"], duration),
        "type": "task",
        "locked": False,
        "completed": False,
        "skipped": False,
        "priority": task.get("priority", "medium"),
        "todoist_id": task.get("id"),
        "duration": duration,
    }
    plan["timeblocks"].append(block)
    plan["timeblocks"].sort(key=lambda b: _time_to_minutes(b["start"]))
    plan["total_tasks"] = plan.get("total_tasks", 0) + 1
    return True, block


def mark_task_complete(plan: dict, task_id: str) -> bool:
    """Mark a task block as completed."""
    for block in plan["timeblocks"]:
        if block.get("id") == task_id or block.get("todoist_id") == task_id:
            block["completed"] = True
            plan["completed_tasks"] = plan.get("completed_tasks", 0) + 1
            total = plan.get("total_tasks", 1)
            plan["completion_rate"] = plan["completed_tasks"] / total * 100
            return True
    return False


async def write_plan_to_todoist(plan: dict) -> tuple[int, int]:
    """
    Write time-box start times and durations back to Todoist for each task block.

    Sets due_datetime (= block start) and duration on every task block that has
    a todoist_id. Returns (updated_count, failed_count).
    """
    from integrations.todoist import update_task

    plan_date = plan.get("date", date.today().isoformat())
    updated = 0
    failed = 0

    for block in plan.get("timeblocks", []):
        if block.get("type") != "task" or not block.get("todoist_id"):
            continue

        task_id = block["todoist_id"]
        start = block.get("start", "")
        duration = block.get("duration", DEFAULT_TASK_DURATION)

        # Build ISO 8601 due_datetime from plan date + block start time
        try:
            due_datetime = f"{plan_date}T{start}:00"
            await update_task(
                task_id,
                due_datetime=due_datetime,
                duration=duration,
                duration_unit="minute",
            )
            updated += 1
        except Exception as e:
            logger.warning("write_plan_to_todoist_failed", task_id=task_id, error=str(e))
            failed += 1

    logger.info("plan_written_to_todoist", updated=updated, failed=failed)
    return updated, failed


def format_plan_for_telegram(plan: dict) -> str:
    """Format the daily plan as a Telegram Markdown message."""
    lines = [f"📅 *Today's Plan — {plan.get('date', '')}*\n"]
    completed = plan.get("completed_tasks", 0)
    total = plan.get("total_tasks", 0)
    lines.append(f"Progress: {completed}/{total} tasks\n")

    for block in plan.get("timeblocks", []):
        start = block.get("start", "")
        end = block.get("end", "")
        title = block.get("title", "")
        btype = block.get("type", "task")

        if btype == "locked":
            lines.append(f"🔒 {start}–{end} {title}")
        elif btype == "calendar":
            lines.append(f"📆 {start}–{end} {title}")
        elif block.get("completed"):
            lines.append(f"✅ {start}–{end} ~~{title}~~")
        elif block.get("skipped"):
            lines.append(f"⏭ {start}–{end} {title}")
        else:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                block.get("priority", "medium"), "🟡"
            )
            lines.append(f"{priority_icon} {start}–{end} {title}")

    if plan.get("pending"):
        lines.append(f"\n📌 *Backlog ({len(plan['pending'])} tasks)*")
        for t in plan["pending"]:
            lines.append(f"  • {t['content']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_available_slots(locked_blocks: list[dict], start: str, end: str) -> list[dict]:
    """Find gaps between locked blocks within [start, end]."""
    slots = []
    cursor = _time_to_minutes(start)
    end_minutes = _time_to_minutes(end)

    sorted_locked = sorted(locked_blocks, key=lambda b: _time_to_minutes(b["start"]))

    for block in sorted_locked:
        block_start = _time_to_minutes(block["start"])
        block_end = _time_to_minutes(block["end"])

        if block_start > cursor and block_end > cursor:
            gap_start = max(cursor, _time_to_minutes(start))
            gap_end = min(block_start, end_minutes)
            if gap_end - gap_start >= 15:
                slots.append({"start": _minutes_to_time(gap_start), "end": _minutes_to_time(gap_end)})

        cursor = max(cursor, block_end)

    # Slot after last locked block
    if cursor < end_minutes:
        slots.append({"start": _minutes_to_time(cursor), "end": _minutes_to_time(end_minutes)})

    return slots


def _find_best_slot(slots: list[dict], duration: int, priority: str) -> Optional[dict]:
    """Find the best slot for a task of given duration and priority."""
    fitting = [
        s for s in slots
        if _time_to_minutes(s["end"]) - _time_to_minutes(s["start"]) >= duration
    ]
    if not fitting:
        return None

    # High priority → prefer morning (earlier slots)
    if priority == "high":
        return fitting[0]

    # Low priority → prefer later slots
    if priority == "low":
        return fitting[-1]

    return fitting[0]
