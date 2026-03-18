from __future__ import annotations
"""Google Calendar integration — fetch today's and upcoming events."""

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from googleapiclient.discovery import build

from integrations.google_auth import get_credentials

logger = structlog.get_logger(__name__)


def _build_service():
    creds = get_credentials()
    if creds is None:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def get_today_events() -> list[dict]:
    """Return calendar events for today (midnight → midnight, local UTC)."""
    return await get_upcoming_events(days=1)


async def get_upcoming_events(days: int = 7) -> list[dict]:
    """Return calendar events for the next `days` days."""
    service = _build_service()
    if service is None:
        logger.info("google_calendar_not_authenticated")
        return []

    now = datetime.now(timezone.utc)
    time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    time_max = (now + timedelta(days=days)).replace(
        hour=23, minute=59, second=59, microsecond=0
    ).isoformat()

    try:
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            )
            .execute()
        )

        events = []
        for item in result.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            events.append(
                {
                    "id": item.get("id"),
                    "summary": item.get("summary", "(no title)"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "location": item.get("location"),
                    "description": item.get("description"),
                    "attendees": [
                        a.get("email") for a in item.get("attendees", [])
                    ],
                }
            )

        logger.info("google_calendar_events_fetched", count=len(events), days=days)
        return events

    except Exception as e:
        logger.warning("google_calendar_fetch_failed", error=str(e))
        return []


async def create_event(
    summary: str,
    start_dt: str,
    end_dt: str,
    description: str = "",
    location: str = "",
) -> dict:
    """
    Create a calendar event.

    Args:
        summary: Event title.
        start_dt: ISO 8601 datetime string (e.g. "2026-03-20T14:00:00+00:00").
        end_dt: ISO 8601 datetime string.
        description: Optional event description/notes.
        location: Optional location string.

    Returns:
        Created event dict, or {"error": ...} on failure.
    """
    service = _build_service()
    if service is None:
        logger.warning("google_calendar_not_authenticated")
        return {"error": "Google Calendar not connected. Run /auth first."}

    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_dt},
        "end": {"dateTime": end_dt},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    try:
        created = service.events().insert(calendarId="primary", body=body).execute()
        logger.info("google_calendar_event_created", summary=summary, event_id=created.get("id"))
        return {
            "id": created.get("id"),
            "summary": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
            "link": created.get("htmlLink"),
        }
    except Exception as e:
        logger.error("google_calendar_create_failed", error=str(e))
        return {"error": str(e)}


_DAY_START_HOUR = 8   # earliest free slot boundary
_DAY_END_HOUR = 22    # latest free slot boundary
_MIN_SLOT_MINUTES = 30


def _parse_dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def get_free_slots(events: list[dict], days: int = 7) -> list[dict]:
    """
    Compute free time windows across `days` days based on calendar events.

    Returns a list of dicts: {"start": datetime, "end": datetime, "duration_minutes": int}
    Only windows >= _MIN_SLOT_MINUTES and within _DAY_START_HOUR–_DAY_END_HOUR are returned.
    """
    now = datetime.now(timezone.utc)
    free_slots = []

    for day_offset in range(days):
        day = now + timedelta(days=day_offset)
        day_start = day.replace(hour=_DAY_START_HOUR, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=_DAY_END_HOUR, minute=0, second=0, microsecond=0)

        # Skip time already past today
        if day_offset == 0:
            day_start = max(day_start, now.replace(second=0, microsecond=0))

        # Collect events that overlap this day
        busy: list[tuple[datetime, datetime]] = []
        for e in events:
            s = _parse_dt(e.get("start"))
            end = _parse_dt(e.get("end"))
            if s and end and s < day_end and end > day_start:
                busy.append((max(s, day_start), min(end, day_end)))

        # Sort and merge overlapping busy blocks
        busy.sort(key=lambda x: x[0])
        merged: list[tuple[datetime, datetime]] = []
        for s, e in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        # Find gaps between busy blocks
        cursor = day_start
        for s, e in merged:
            if s > cursor:
                duration = int((s - cursor).total_seconds() / 60)
                if duration >= _MIN_SLOT_MINUTES:
                    free_slots.append({"start": cursor, "end": s, "duration_minutes": duration})
            cursor = max(cursor, e)

        if cursor < day_end:
            duration = int((day_end - cursor).total_seconds() / 60)
            if duration >= _MIN_SLOT_MINUTES:
                free_slots.append({"start": cursor, "end": day_end, "duration_minutes": duration})

    return free_slots


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%a %d %b %H:%M")


def _format_event(event: dict) -> str:
    """Format a single event into a human-readable string."""
    start = event["start"] or "?"
    if "T" in start:
        dt = _parse_dt(start)
        if dt:
            start = _fmt_dt(dt)
    summary = event["summary"]
    location = f" @ {event['location']}" if event.get("location") else ""
    attendees = ""
    if event.get("attendees"):
        attendees = f" (with {', '.join(event['attendees'][:3])})"
    return f"- {start}: {summary}{location}{attendees}"


def format_events_for_context(events: list[dict], days: int = 7) -> str:
    """Return a plain-text block with calendar events AND free slots for context injection."""
    lines = []

    if events:
        lines.append("User's upcoming calendar events:")
        lines.extend(_format_event(e) for e in events)
    else:
        lines.append("User has no upcoming calendar events.")

    lines.append("")
    free = get_free_slots(events, days=days)
    if free:
        lines.append("User's free time windows (available to book):")
        for slot in free[:10]:  # cap at 10 slots to avoid bloat
            hrs = slot["duration_minutes"] // 60
            mins = slot["duration_minutes"] % 60
            duration_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
            lines.append(f"- {_fmt_dt(slot['start'])} → {_fmt_dt(slot['end'])} ({duration_str} free)")
    else:
        lines.append("No significant free windows found in the next week.")

    return "\n".join(lines)
