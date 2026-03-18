from __future__ import annotations
"""
RoutineAgent - Manages habits and daily routines.

Responsibilities:
- Track habit completion
- Analyze patterns and trends
- Send motivational reminders
- Suggest routine adjustments
- Provide insights on productivity
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict

from .base import BaseAgent

logger = structlog.get_logger()


class RoutineAgent(BaseAgent):
    """Agent specialized in habit tracking and routine optimization."""

    def __init__(self):
        """Initialize the RoutineAgent."""
        super().__init__(
            name="RoutineAgent",
            description="Tracks habits, suggests routines, and analyzes patterns",
            capabilities=[
                "track_habits",
                "log_completion",
                "analyze_patterns",
                "suggest_adjustment",
                "send_reminder",
                "get_streak",
                "identify_blockers",
                "motivational_nudge",
            ],
        )

        # Common daily routines
        self.default_routines = {
            "morning_standup": {
                "title": "Morning standup",
                "time": "09:00",
                "category": "work",
                "duration": 30,
            },
            "gym": {
                "title": "Exercise",
                "time": "17:00",
                "category": "health",
                "duration": 60,
            },
            "reflection": {
                "title": "Evening reflection",
                "time": "21:00",
                "category": "personal",
                "duration": 15,
            },
            "reading": {
                "title": "Read for 20 minutes",
                "time": "21:30",
                "category": "learning",
                "duration": 20,
            },
        }

    @property
    def system_prompt(self) -> str:
        """System prompt for habit and routine decisions."""
        return """You are a habit and routine coach for Hanzalah, a 24-year-old data engineer.

Your role is to:
1. Help build sustainable daily routines
2. Track progress without judgment
3. Identify patterns and bottlenecks
4. Suggest realistic improvements
5. Provide motivational support

PERSONALITY:
- Supportive and non-judgmental
- Data-driven insights
- Understand that consistency beats perfection
- Recognize effort and small wins
- Honest about patterns

HABIT SCIENCE PRINCIPLES:
- Streaks build momentum (celebrate 7, 14, 30-day streaks)
- Identify barriers to completion (time, energy, motivation)
- Connect habits to values and goals
- Suggest adjustments based on patterns
- Small improvements compound

COACHING STYLE:
- Celebrate wins
- Normalize skipped days
- Identify true barriers vs. excuses
- Suggest realistic adjustments
- Make routines tied to existing anchors
"""

    async def get_routines(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get all tracked routines.

        Args:
            context: Current context

        Returns:
            Dict of routines with their status
        """
        self._logger.info("fetching_routines")

        routines = context.get("routines", {})

        if not routines:
            # Return default routines if none exist
            routines = self.default_routines

        # Enrich with status
        today = datetime.now().strftime("%Y-%m-%d")
        enriched = {}

        for routine_id, routine in routines.items():
            completion_history = context.get(
                f"routine_{routine_id}_history",
                []
            )
            today_completed = any(
                h["date"] == today and h["completed"]
                for h in completion_history
            )

            enriched[routine_id] = {
                **routine,
                "id": routine_id,
                "completed_today": today_completed,
                "streak": self._calculate_streak(routine_id, context),
                "completion_rate": self._calculate_completion_rate(
                    routine_id,
                    context
                ),
            }

        self._logger.info("routines_fetched", count=len(enriched))

        return enriched

    async def check_completion(
        self,
        context: Dict[str, Any],
        routine_id: str,
        completed: bool = True,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Log routine completion.

        Args:
            context: Current context
            routine_id: ID of routine to mark
            completed: Whether routine was completed
            notes: Optional notes about completion

        Returns:
            Updated routine status
        """
        today = datetime.now().strftime("%Y-%m-%d")

        self._logger.info(
            "logging_routine",
            routine=routine_id,
            completed=completed,
        )

        # Get or create history for this routine
        history_key = f"routine_{routine_id}_history"
        history = context.get(history_key, [])

        # Add entry
        entry = {
            "date": today,
            "completed": completed,
            "timestamp": datetime.now().isoformat(),
            "notes": notes,
        }
        history.append(entry)

        # Calculate updated metrics
        streak = self._calculate_streak(routine_id, context, include_today=True)
        completion_rate = self._calculate_completion_rate(routine_id, context)

        result = {
            "routine_id": routine_id,
            "date": today,
            "completed": completed,
            "streak": streak,
            "completion_rate": completion_rate,
            "message": self._get_completion_message(
                routine_id,
                completed,
                streak,
            ),
        }

        self._logger.info(
            "routine_logged",
            routine=routine_id,
            streak=streak,
            completion_rate=f"{completion_rate:.1f}%",
        )

        return result

    async def analyze_patterns(
        self,
        context: Dict[str, Any],
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """
        Analyze routine completion patterns.

        Args:
            context: Current context
            days_back: Number of days to analyze

        Returns:
            Pattern analysis with insights
        """
        self._logger.info("analyzing_patterns", days_back=days_back)

        routines = await self.get_routines(context)
        patterns = {}

        for routine_id, routine in routines.items():
            history_key = f"routine_{routine_id}_history"
            history = context.get(history_key, [])

            # Filter to time window
            cutoff = (
                datetime.now() - timedelta(days=days_back)
            ).strftime("%Y-%m-%d")
            recent = [h for h in history if h["date"] >= cutoff]

            if not recent:
                continue

            # Calculate stats
            completed_count = sum(1 for h in recent if h["completed"])
            total_count = len(recent)
            completion_rate = (completed_count / total_count * 100) if total_count else 0

            # Analyze by day of week
            day_stats = defaultdict(lambda: {"completed": 0, "total": 0})
            for h in recent:
                try:
                    day_name = datetime.strptime(
                        h["date"],
                        "%Y-%m-%d"
                    ).strftime("%A")
                    day_stats[day_name]["total"] += 1
                    if h["completed"]:
                        day_stats[day_name]["completed"] += 1
                except (ValueError, KeyError):
                    pass

            # Calculate weakest day
            weakest_day = self._find_weakest_day(day_stats)

            patterns[routine_id] = {
                "routine": routine.get("title", routine_id),
                "completion_rate": f"{completion_rate:.1f}%",
                "completed": completed_count,
                "total": total_count,
                "trend": self._calculate_trend(recent),
                "weakest_day": weakest_day,
                "day_breakdown": dict(day_stats),
            }

        analysis = {
            "period_days": days_back,
            "routines_analyzed": len(patterns),
            "patterns": patterns,
            "insights": self._generate_insights(patterns),
        }

        self._logger.info(
            "patterns_analyzed",
            routines_count=len(patterns),
        )

        return analysis

    async def suggest_adjustment(
        self,
        context: Dict[str, Any],
        routine_id: str,
    ) -> Dict[str, Any]:
        """
        Suggest adjustments to improve routine completion.

        Args:
            context: Current context
            routine_id: Routine to improve

        Returns:
            Suggested adjustments with reasoning
        """
        self._logger.info("suggesting_adjustment", routine=routine_id)

        routines = await self.get_routines(context)
        routine = routines.get(routine_id, {})

        if not routine:
            return {"error": f"Routine {routine_id} not found"}

        # Analyze patterns for this routine
        history_key = f"routine_{routine_id}_history"
        history = context.get(history_key, [])

        # Find weakest day
        day_stats = defaultdict(lambda: {"completed": 0, "total": 0})
        for h in history[-30:]:  # Last 30 days
            try:
                day_name = datetime.strptime(
                    h["date"],
                    "%Y-%m-%d"
                ).strftime("%A")
                day_stats[day_name]["total"] += 1
                if h["completed"]:
                    day_stats[day_name]["completed"] += 1
            except (ValueError, KeyError):
                pass

        weakest_day = self._find_weakest_day(day_stats)
        completion_rate = self._calculate_completion_rate(routine_id, context)

        suggestions = []

        # Suggestion 1: Time adjustment
        if completion_rate < 50:
            suggestions.append({
                "type": "time_adjustment",
                "title": "Change scheduled time",
                "reason": f"Low completion rate ({completion_rate:.0f}%)",
                "action": f"Try scheduling {routine.get('title')} 30 minutes earlier or later",
            })

        # Suggestion 2: Break it down
        if routine.get("duration", 0) > 45:
            suggestions.append({
                "type": "reduce_scope",
                "title": "Start smaller",
                "reason": "Large time commitment may be barrier",
                "action": f"Reduce from {routine.get('duration')}min to 15min sessions",
            })

        # Suggestion 3: Anchor to existing habit
        if weakest_day:
            suggestions.append({
                "type": "anchor_habit",
                "title": "Link to an existing routine",
                "reason": f"Particularly struggles on {weakest_day}s",
                "action": f"Anchor to another activity (e.g., 'do this after lunch')",
            })

        # Suggestion 4: Environmental change
        if completion_rate < 70:
            suggestions.append({
                "type": "environment",
                "title": "Change environment",
                "reason": "External factors may help",
                "action": "Try a different location or set up reminders/environment cues",
            })

        self._logger.info(
            "suggestions_generated",
            routine=routine_id,
            count=len(suggestions),
        )

        return {
            "routine_id": routine_id,
            "routine_title": routine.get("title"),
            "current_completion_rate": f"{completion_rate:.1f}%",
            "weakest_day": weakest_day,
            "suggestions": suggestions,
        }

    async def identify_blockers(
        self,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Identify what's preventing routine completion.

        Args:
            context: Current context

        Returns:
            List of blockers with severity
        """
        self._logger.info("identifying_blockers")

        routines = await self.get_routines(context)
        blockers = []

        for routine_id, routine in routines.items():
            completion_rate = self._calculate_completion_rate(routine_id, context)

            if completion_rate < 60:
                # This routine has issues
                history_key = f"routine_{routine_id}_history"
                history = context.get(history_key, [])

                # Analyze what's happening
                recent_failures = [
                    h for h in history[-14:]
                    if not h.get("completed")
                ]

                blocker = {
                    "routine": routine.get("title"),
                    "routine_id": routine_id,
                    "severity": "high" if completion_rate < 40 else "medium",
                    "completion_rate": f"{completion_rate:.1f}%",
                    "recent_failures": len(recent_failures),
                    "possible_causes": self._diagnose_blockers(
                        routine,
                        history,
                        context
                    ),
                }
                blockers.append(blocker)

        blockers.sort(
            key=lambda b: (b["severity"] == "high", b["completion_rate"]),
            reverse=True
        )

        self._logger.info("blockers_identified", count=len(blockers))

        return blockers

    async def send_reminder(
        self,
        routine_id: str,
        routine: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate reminder for a routine.

        Args:
            routine_id: Routine to remind about
            routine: Routine details

        Returns:
            Reminder message
        """
        self._logger.info("sending_reminder", routine=routine_id)

        title = routine.get("title", "Routine")
        time = routine.get("time", "")
        category = routine.get("category", "general")

        # Generate contextual message
        if category == "health":
            message = f"💪 Time for {title}! Your body will thank you."
        elif category == "work":
            message = f"📊 {title} starting soon. Let's get focused!"
        elif category == "learning":
            message = f"📚 Ready to learn? {title} time!"
        else:
            message = f"🔔 Reminder: {title} at {time}"

        return {
            "routine": routine_id,
            "title": title,
            "scheduled_time": time,
            "message": message,
            "category": category,
        }

    # Helper methods

    def _calculate_streak(
        self,
        routine_id: str,
        context: Dict[str, Any],
        include_today: bool = False,
    ) -> int:
        """Calculate current streak for a routine."""
        history_key = f"routine_{routine_id}_history"
        history = context.get(history_key, [])

        if not history:
            return 0

        # Sort by date
        sorted_history = sorted(
            history,
            key=lambda h: h.get("date", ""),
            reverse=True
        )

        streak = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for entry in sorted_history:
            entry_date = entry.get("date", "")

            # Skip today if we're checking history before completion
            if entry_date == today and not include_today:
                continue

            if entry.get("completed"):
                streak += 1
            else:
                break

        return streak

    def _calculate_completion_rate(
        self,
        routine_id: str,
        context: Dict[str, Any],
        days: int = 30,
    ) -> float:
        """Calculate completion rate for a routine."""
        history_key = f"routine_{routine_id}_history"
        history = context.get(history_key, [])

        if not history:
            return 0.0

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = [h for h in history if h.get("date", "") >= cutoff]

        if not recent:
            return 0.0

        completed = sum(1 for h in recent if h.get("completed"))
        return (completed / len(recent) * 100)

    def _calculate_trend(self, history: List[Dict]) -> str:
        """Calculate trend (improving, declining, stable)."""
        if len(history) < 7:
            return "insufficient_data"

        # Compare first half to second half
        midpoint = len(history) // 2
        first_half = sum(1 for h in history[:midpoint] if h.get("completed"))
        second_half = sum(1 for h in history[midpoint:] if h.get("completed"))

        first_rate = (first_half / midpoint * 100) if midpoint else 0
        second_rate = (second_half / (len(history) - midpoint) * 100) if (len(history) - midpoint) else 0

        if second_rate > first_rate + 10:
            return "improving"
        elif second_rate < first_rate - 10:
            return "declining"
        else:
            return "stable"

    def _find_weakest_day(self, day_stats: Dict) -> Optional[str]:
        """Find the day of week with lowest completion rate."""
        if not day_stats:
            return None

        day_rates = {}
        for day, stats in day_stats.items():
            total = stats["total"]
            if total > 0:
                rate = stats["completed"] / total
                day_rates[day] = rate

        if not day_rates:
            return None

        return min(day_rates, key=day_rates.get)

    def _generate_insights(self, patterns: Dict) -> List[str]:
        """Generate insights from patterns."""
        insights = []

        # Find best and worst routines
        if patterns:
            best = max(
                patterns.items(),
                key=lambda x: float(x[1]["completion_rate"].rstrip("%"))
            )
            worst = min(
                patterns.items(),
                key=lambda x: float(x[1]["completion_rate"].rstrip("%"))
            )

            insights.append(
                f"Your best habit is '{best[1]['routine']}' "
                f"({best[1]['completion_rate']} completion rate)."
            )
            insights.append(
                f"Focus on improving '{worst[1]['routine']}' "
                f"({worst[1]['completion_rate']} completion rate)."
            )

        return insights

    def _diagnose_blockers(
        self,
        routine: Dict[str, Any],
        history: List[Dict],
        context: Dict[str, Any],
    ) -> List[str]:
        """Diagnose what's blocking a routine."""
        blockers = []

        time = routine.get("time", "")
        duration = routine.get("duration", 0)

        if duration > 60:
            blockers.append("Long duration - consider breaking into smaller steps")

        if time and int(time.split(":")[0]) >= 17:
            blockers.append("Evening timing - might conflict with energy levels or plans")

        # Check recent gaps
        recent_failure_streak = 0
        for h in reversed(history[-7:]):
            if not h.get("completed"):
                recent_failure_streak += 1
            else:
                break

        if recent_failure_streak >= 3:
            blockers.append(f"Recent {recent_failure_streak}-day streak of failures")

        return blockers or ["Check for schedule conflicts or changing priorities"]

    def _get_completion_message(
        self,
        routine_id: str,
        completed: bool,
        streak: int,
    ) -> str:
        """Generate a message for routine completion."""
        if not completed:
            return "No worries, you can catch up tomorrow!"

        if streak == 1:
            return "Great start! Keep it going! 🎯"
        elif streak == 7:
            return "Amazing! One week streak! 🔥"
        elif streak == 30:
            return "Incredible! 30-day streak! You're a champion! 🏆"
        elif streak % 10 == 0:
            return f"Awesome! {streak}-day streak! 💪"
        else:
            return f"Nice! {streak}-day streak going! 👏"
