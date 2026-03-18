from __future__ import annotations
"""
SchedulerAgent - Manages calendar and task scheduling.

Responsibilities:
- Read and understand calendar availability
- Find optimal free time slots
- Suggest scheduling based on priorities
- Create calendar events
- Provide morning briefings and end-of-day reviews
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseAgent, PlanStep

logger = structlog.get_logger()


class SchedulerAgent(BaseAgent):
    """Agent specialized in time management and calendar optimization."""

    def __init__(self):
        """Initialize the SchedulerAgent."""
        super().__init__(
            name="SchedulerAgent",
            description="Manages calendar, finds free time, and suggests optimal scheduling",
            capabilities=[
                "read_calendar",
                "find_free_slots",
                "suggest_scheduling",
                "create_events",
                "check_task_completion",
                "provide_morning_briefing",
                "end_of_day_review",
            ],
        )

    @property
    def system_prompt(self) -> str:
        """System prompt for scheduling decisions."""
        return """You are a personal scheduling assistant for Hanzalah, a 24-year-old data engineer.

Your role is to optimize his time by:
1. Understanding his calendar and commitments
2. Finding optimal free slots for new tasks
3. Suggesting when to schedule activities based on energy levels and priorities
4. Managing task deadlines and reminders
5. Providing daily briefings and reviews

PERSONALITY:
- Proactive and detail-oriented
- Respectful of focus time (don't over-schedule)
- Aware that early morning and late afternoon are good for deep work
- Lunch time: 12-1pm
- Evenings flexible for personal/social activities

DECISION RULES:
- Back-to-back meetings reduce productivity; suggest 15min buffers
- Group similar tasks together
- Schedule important work during peak energy (usually mornings for Hanzalah)
- Consider time zones if applicable
- Always confirm before creating events

RESPONSE STYLE:
- Concise and actionable
- Provide specific time recommendations
- Explain reasoning when suggesting schedules
- Highlight conflicts or concerns
"""

    async def get_today_schedule(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get today's calendar schedule.

        Args:
            context: Current context with calendar state

        Returns:
            Dict with today's events and free slots
        """
        self._logger.info("getting_today_schedule")

        events = context.get("calendar_events", [])
        now = datetime.now()

        today_events = [
            e for e in events
            if e.get("date") == now.strftime("%Y-%m-%d")
        ]

        # Sort by time
        today_events.sort(key=lambda e: e.get("start_time", ""))

        return {
            "date": now.strftime("%Y-%m-%d"),
            "total_events": len(today_events),
            "events": today_events,
            "workday_start": "09:00",
            "workday_end": "17:00",
        }

    async def find_free_slots(
        self,
        context: Dict[str, Any],
        duration_minutes: int = 30,
        date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find free time slots on a given date.

        Args:
            context: Current context with calendar data
            duration_minutes: Minimum duration needed
            date: Specific date (defaults to today)

        Returns:
            List of available time slots
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        self._logger.info(
            "finding_free_slots",
            date=date,
            duration=duration_minutes,
        )

        events = context.get("calendar_events", [])
        target_events = [
            e for e in events
            if e.get("date") == date
        ]

        # Parse working hours
        workday_start = self._parse_time("09:00")
        workday_end = self._parse_time("17:00")

        # Build busy intervals
        busy_intervals = []
        for event in sorted(target_events, key=lambda e: e.get("start_time", "")):
            start = self._parse_time(event.get("start_time", ""))
            end = self._parse_time(event.get("end_time", ""))
            if start and end:
                busy_intervals.append((start, end))

        # Merge overlapping intervals
        merged = self._merge_intervals(busy_intervals)

        # Find free slots
        free_slots = []
        current_time = workday_start

        for busy_start, busy_end in merged:
            if current_time < busy_start:
                gap_duration = (busy_start - current_time).total_seconds() / 60
                if gap_duration >= duration_minutes:
                    free_slots.append({
                        "start": current_time.strftime("%H:%M"),
                        "end": busy_start.strftime("%H:%M"),
                        "duration_minutes": int(gap_duration),
                    })
            current_time = max(current_time, busy_end)

        # Check final slot
        if current_time < workday_end:
            gap_duration = (workday_end - current_time).total_seconds() / 60
            if gap_duration >= duration_minutes:
                free_slots.append({
                    "start": current_time.strftime("%H:%M"),
                    "end": workday_end.strftime("%H:%M"),
                    "duration_minutes": int(gap_duration),
                })

        self._logger.info(
            "free_slots_found",
            count=len(free_slots),
            date=date,
        )

        return free_slots

    async def suggest_time(
        self,
        context: Dict[str, Any],
        task_type: str,
        priority: str = "medium",
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Suggest optimal time for a task or meeting.

        Args:
            context: Current context
            task_type: Type of task (e.g., "deep_work", "meeting", "exercise")
            priority: Priority level (low, medium, high)
            attendees: List of attendees if it's a meeting

        Returns:
            Suggested time with reasoning
        """
        self._logger.info(
            "suggesting_time",
            task_type=task_type,
            priority=priority,
            attendees_count=len(attendees) if attendees else 0,
        )

        # Get today's free slots
        free_slots = await self.find_free_slots(context, duration_minutes=60)

        if not free_slots:
            return {
                "available": False,
                "suggestion": "No free slots available today. Consider scheduling for tomorrow.",
                "reason": "Calendar is fully booked",
            }

        # Score slots based on task type
        scored_slots = []
        for slot in free_slots:
            score = self._score_time_slot(
                slot["start"],
                task_type,
                priority,
            )
            scored_slots.append({**slot, "score": score})

        # Sort by score
        scored_slots.sort(key=lambda s: s["score"], reverse=True)
        best_slot = scored_slots[0]

        return {
            "available": True,
            "suggested_time": best_slot["start"],
            "end_time": best_slot["end"],
            "duration_minutes": best_slot["duration_minutes"],
            "score": best_slot["score"],
            "reasoning": self._get_time_reasoning(
                best_slot["start"],
                task_type,
            ),
            "alternatives": [
                {
                    "time": s["start"],
                    "end": s["end"],
                    "score": s["score"],
                }
                for s in scored_slots[1:4]  # Top 3 alternatives
            ],
        }

    async def create_event(
        self,
        context: Dict[str, Any],
        title: str,
        start_time: str,
        duration_minutes: int = 60,
        description: str = "",
        attendees: Optional[List[str]] = None,
        date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a calendar event.

        Args:
            context: Current context
            title: Event title
            start_time: Start time (HH:MM format)
            duration_minutes: Event duration
            description: Event description
            attendees: List of attendee emails
            date: Date for the event (defaults to today)

        Returns:
            Created event details
        """
        date = date or datetime.now().strftime("%Y-%m-%d")

        self._logger.info(
            "creating_event",
            title=title,
            date=date,
            start_time=start_time,
            attendees_count=len(attendees) if attendees else 0,
        )

        # Calculate end time
        start = self._parse_time(start_time)
        end = start + timedelta(minutes=duration_minutes)

        event = {
            "id": self._generate_event_id(),
            "title": title,
            "date": date,
            "start_time": start_time,
            "end_time": end.strftime("%H:%M"),
            "duration_minutes": duration_minutes,
            "description": description,
            "attendees": attendees or [],
            "created_at": datetime.now().isoformat(),
            "status": "scheduled",
        }

        self._logger.info(
            "event_created",
            event_id=event["id"],
            title=title,
        )

        return event

    async def check_task_completion(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check today's task completion status.

        Args:
            context: Current context with tasks

        Returns:
            Task completion summary
        """
        self._logger.info("checking_task_completion")

        tasks = context.get("tasks", [])
        today = datetime.now().strftime("%Y-%m-%d")

        today_tasks = [
            t for t in tasks
            if t.get("date") == today
        ]

        completed = [t for t in today_tasks if t.get("completed")]
        pending = [t for t in today_tasks if not t.get("completed")]

        completion_rate = (
            (len(completed) / len(today_tasks) * 100)
            if today_tasks
            else 0
        )

        return {
            "date": today,
            "total_tasks": len(today_tasks),
            "completed": len(completed),
            "pending": len(pending),
            "completion_rate": f"{completion_rate:.1f}%",
            "pending_tasks": pending,
            "completed_tasks": completed,
        }

    async def provide_morning_briefing(
        self,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate a morning briefing for the day.

        Args:
            context: Current context

        Returns:
            Morning briefing message
        """
        self._logger.info("generating_morning_briefing")

        schedule = await self.get_today_schedule(context)
        free_slots = await self.find_free_slots(context)
        tasks = context.get("tasks", [])
        today = datetime.now().strftime("%Y-%m-%d")
        today_tasks = [t for t in tasks if t.get("date") == today]

        briefing = f"""Good morning! Here's your day at a glance:

📅 SCHEDULE:
- Total events today: {schedule['total_events']}
{self._format_events(schedule['events'])}

⏰ FREE TIME:
- Available slots: {len(free_slots)}
{self._format_free_slots(free_slots[:3])}

✅ TODAY'S TASKS:
- Total: {len(today_tasks)}
{self._format_tasks(today_tasks)}

💡 FOCUS TIME: You have {sum(s['duration_minutes'] for s in free_slots)} minutes of potential focus time.
"""

        return briefing

    async def end_of_day_review(
        self,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate an end-of-day review.

        Args:
            context: Current context

        Returns:
            End-of-day review message
        """
        self._logger.info("generating_end_of_day_review")

        completion = await self.check_task_completion(context)
        events = context.get("calendar_events", [])
        today = datetime.now().strftime("%Y-%m-%d")
        today_events = [e for e in events if e.get("date") == today]

        review = f"""📊 END OF DAY REVIEW

✅ COMPLETED TASKS: {completion['completed']} of {completion['total_tasks']}
({completion['completion_rate']} completion rate)

📅 ATTENDED EVENTS: {len(today_events)}

📝 SUMMARY:
{'Great job! You completed all your tasks today.' if completion['pending'] == 0 else f'You have {completion["pending"]} pending tasks to carry over.'}

💭 REFLECTION:
- What went well today?
- What could be improved?
- Any blockers to address?
"""

        return review

    # Helper methods

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string (HH:MM) to datetime object."""
        try:
            hour, minute = map(int, time_str.split(":"))
            now = datetime.now()
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            return None

    def _merge_intervals(
        self,
        intervals: List[tuple],
    ) -> List[tuple]:
        """Merge overlapping time intervals."""
        if not intervals:
            return []

        sorted_intervals = sorted(intervals)
        merged = [sorted_intervals[0]]

        for current_start, current_end in sorted_intervals[1:]:
            last_start, last_end = merged[-1]

            if current_start <= last_end:
                # Overlapping, merge
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                # Non-overlapping, add new interval
                merged.append((current_start, current_end))

        return merged

    def _score_time_slot(
        self,
        time_str: str,
        task_type: str,
        priority: str,
    ) -> float:
        """Score a time slot based on task type and time."""
        try:
            hour = int(time_str.split(":")[0])
        except (ValueError, IndexError):
            return 0.5

        # Base score on time of day
        score = 0.0

        # Morning hours (9-12) - best for deep work
        if 9 <= hour < 12:
            score = 0.9
        # Early afternoon (12-14) - after lunch dip
        elif 12 <= hour < 14:
            score = 0.6
        # Mid afternoon (14-16) - second wind
        elif 14 <= hour < 16:
            score = 0.8
        # Late afternoon (16-17) - wind down
        elif 16 <= hour < 17:
            score = 0.7
        else:
            score = 0.5

        # Adjust for task type
        if task_type == "deep_work":
            if 9 <= hour < 12:
                score = min(1.0, score + 0.2)
        elif task_type == "meeting":
            score += 0.1  # Meetings can be anytime
        elif task_type == "exercise":
            if hour in [12, 17, 18]:
                score = min(1.0, score + 0.2)

        # Adjust for priority
        if priority == "high":
            score = min(1.0, score + 0.1)

        return score

    def _get_time_reasoning(self, time_str: str, task_type: str) -> str:
        """Get reasoning for suggested time."""
        try:
            hour = int(time_str.split(":")[0])
        except (ValueError, IndexError):
            return "Suggested time available"

        if 9 <= hour < 12:
            return "Morning slot is ideal for deep focus work"
        elif 14 <= hour < 16:
            return "Afternoon slot after lunch, good for focused work"
        elif hour >= 17:
            return "Evening slot good for personal activities"
        else:
            return "Time slot available"

    def _format_events(self, events: List[Dict]) -> str:
        """Format events for display."""
        if not events:
            return "  (No events scheduled)"
        return "\n".join(
            f"  • {e.get('title', 'Event')} at {e.get('start_time', '?')}"
            for e in events[:5]
        )

    def _format_free_slots(self, slots: List[Dict]) -> str:
        """Format free slots for display."""
        if not slots:
            return "  (No free slots)"
        return "\n".join(
            f"  • {s['start']}-{s['end']} ({s['duration_minutes']}min)"
            for s in slots
        )

    def _format_tasks(self, tasks: List[Dict]) -> str:
        """Format tasks for display."""
        if not tasks:
            return "  (No tasks)"
        return "\n".join(
            f"  {'✓' if t.get('completed') else '○'} {t.get('title', 'Task')}"
            for t in tasks[:5]
        )

    def _generate_event_id(self) -> str:
        """Generate a unique event ID."""
        import uuid
        return f"evt_{uuid.uuid4().hex[:12]}"
