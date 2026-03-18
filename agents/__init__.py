from __future__ import annotations
"""
Agent registry for the personal AI agent system.

Imports and registers all specialized agents.
Provides AGENT_REGISTRY mapping intent strings to agent classes.
"""

from typing import Dict
from .base import BaseAgent, PlanStep, ExecutionResult, ActionType
from .scheduler import SchedulerAgent
from .inbox import InboxAgent
from .routine import RoutineAgent
from .shopping import ShoppingAgent
from .relationship import RelationshipAgent
from .concierge import ConciergeAgent


# Agent registry mapping intent keywords to agent classes
AGENT_REGISTRY = {
    # Scheduling and calendar management
    "schedule": SchedulerAgent,
    "calendar": SchedulerAgent,
    "meeting": SchedulerAgent,
    "free_time": SchedulerAgent,
    "availability": SchedulerAgent,
    "task": SchedulerAgent,
    "event": SchedulerAgent,
    "morning": SchedulerAgent,
    "evening": SchedulerAgent,
    "briefing": SchedulerAgent,
    "review": SchedulerAgent,

    # Email and inbox management
    "email": InboxAgent,
    "inbox": InboxAgent,
    "mail": InboxAgent,
    "message": InboxAgent,
    "reply": InboxAgent,
    "draft": InboxAgent,
    "read": InboxAgent,
    "summarize": InboxAgent,
    "prioritize": InboxAgent,

    # Habits and routines
    "habit": RoutineAgent,
    "routine": RoutineAgent,
    "goal": RoutineAgent,
    "exercise": RoutineAgent,
    "workout": RoutineAgent,
    "track": RoutineAgent,
    "completion": RoutineAgent,
    "reminder": RoutineAgent,
    "motivation": RoutineAgent,

    # Shopping and purchasing
    "shopping": ShoppingAgent,
    "list": ShoppingAgent,
    "buy": ShoppingAgent,
    "purchase": ShoppingAgent,
    "price": ShoppingAgent,
    "deal": ShoppingAgent,
    "budget": ShoppingAgent,
    "want": ShoppingAgent,
    "need": ShoppingAgent,

    # Relationships
    "date": RelationshipAgent,
    "girlfriend": RelationshipAgent,
    "relationship": RelationshipAgent,
    "romantic": RelationshipAgent,
    "anniversary": RelationshipAgent,
    "birthday": RelationshipAgent,
    "gift": RelationshipAgent,
    "preference": RelationshipAgent,

    # Local discovery and booking
    "restaurant": ConciergeAgent,
    "event": ConciergeAgent,
    "activity": ConciergeAgent,
    "discover": ConciergeAgent,
    "book": ConciergeAgent,
    "reservation": ConciergeAgent,
    "venue": ConciergeAgent,
    "entertainment": ConciergeAgent,
}

# Agent descriptions for dispatcher
AGENT_DESCRIPTIONS = {
    SchedulerAgent: "Manages calendar, schedules meetings, finds free time, and provides daily briefings",
    InboxAgent: "Handles email triage, prioritizes messages, summarizes content, and drafts replies",
    RoutineAgent: "Tracks habits, analyzes patterns, suggests improvements, and provides motivation",
    ShoppingAgent: "Manages shopping lists, compares prices, suggests timing, and tracks spending",
    RelationshipAgent: "Manages relationship details, suggests dates, creates content, and tracks important dates",
    ConciergeAgent: "Discovers events, finds restaurants, suggests activities, and handles bookings",
}

# Define all exportable symbols
__all__ = [
    "BaseAgent",
    "PlanStep",
    "ExecutionResult",
    "ActionType",
    "SchedulerAgent",
    "InboxAgent",
    "RoutineAgent",
    "ShoppingAgent",
    "RelationshipAgent",
    "ConciergeAgent",
    "AGENT_REGISTRY",
    "AGENT_DESCRIPTIONS",
]


def get_agent_for_intent(intent: str) -> type:
    """
    Get the appropriate agent class for a given intent.

    Args:
        intent: User intent or keyword

    Returns:
        Agent class that handles this intent
    """
    intent_lower = intent.lower().strip()

    # Exact match
    if intent_lower in AGENT_REGISTRY:
        return AGENT_REGISTRY[intent_lower]

    # Substring match (first match wins)
    for keyword, agent_class in AGENT_REGISTRY.items():
        if keyword in intent_lower:
            return AGENT_REGISTRY[keyword]

    # Default to ConciergeAgent for discovery tasks
    return ConciergeAgent


def get_all_agents() -> Dict[str, type]:
    """
    Get all available agents.

    Returns:
        Dict mapping agent names to agent classes
    """
    from typing import Dict

    return {
        agent.__name__: agent
        for agent in [
            SchedulerAgent,
            InboxAgent,
            RoutineAgent,
            ShoppingAgent,
            RelationshipAgent,
            ConciergeAgent,
        ]
    }
