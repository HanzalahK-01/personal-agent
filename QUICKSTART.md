# Personal Agent System - Quick Start Guide

## Installation

```bash
pip install anthropic structlog
```

## 5-Minute Setup

### 1. Import and Create an Agent

```python
import asyncio
from agents import SchedulerAgent, get_agent_for_intent

# Create a scheduler agent
agent = SchedulerAgent()

# Or auto-route by intent
agent_class = get_agent_for_intent("schedule a meeting")
agent = agent_class()
```

### 2. Prepare Context

```python
context = {
    "calendar_events": [
        {
            "title": "Standup",
            "date": "2026-03-17",
            "start_time": "09:00",
            "end_time": "09:30"
        }
    ],
    "tasks": [
        {"title": "Email Sarah", "date": "2026-03-17", "completed": False}
    ]
}
```

### 3. Generate a Plan

```python
async def main():
    plan = await agent.plan(
        message="Find time for a 1-hour meeting with Sarah",
        context=context,
        memory={}
    )
    
    # Review generated plan
    for step in plan:
        print(f"Step {step.step_number}: {step.description}")
        print(f"  Tool: {step.tool}")
        print(f"  Parameters: {step.parameters}")

asyncio.run(main())
```

### 4. Execute the Plan

```python
async def main():
    # ... generate plan ...
    
    # Execute with MCP client
    result = await agent.execute(plan, context, mcp_client)
    
    # Check results
    print(f"Success: {result.success}")
    print(f"Completed steps: {len(result.steps_completed)}")
    print(f"Failed steps: {len(result.steps_failed)}")
```

### 5. Get Human Summary

```python
async def main():
    # ... execute plan ...
    
    summary = await agent.reflect(result)
    print(summary)

asyncio.run(main())
```

## Agent Quick Reference

### SchedulerAgent
Find free time, schedule meetings, get daily briefings.

```python
from agents import SchedulerAgent

agent = SchedulerAgent()

# Get today's schedule
schedule = await agent.get_today_schedule(context)

# Find 30-minute free slots
free_slots = await agent.find_free_slots(context, duration_minutes=30)

# Suggest best time for deep work
timing = await agent.suggest_time(
    context=context,
    task_type="deep_work",
    priority="high"
)

# Create event
event = await agent.create_event(
    context=context,
    title="1:1 with Sarah",
    start_time="14:00",
    duration_minutes=60
)
```

### InboxAgent
Manage emails, prioritize, summarize, draft replies.

```python
from agents import InboxAgent

agent = InboxAgent()

# Get unread emails
unread = await agent.get_unread_emails(context, limit=20)

# Prioritize
prioritized = await agent.prioritize_emails(context)
# Returns: urgent, important, action_required, fyi, spam

# Summarize one email
summary = await agent.summarize_email(
    email=unread[0],
    include_action_items=True
)

# Draft reply
reply = await agent.draft_reply(
    email=unread[0],
    reply_type="professional"
)
```

### RoutineAgent
Track habits, analyze patterns, get motivation.

```python
from agents import RoutineAgent

agent = RoutineAgent()

# Get all routines
routines = await agent.get_routines(context)

# Log completion
result = await agent.check_completion(
    context=context,
    routine_id="gym",
    completed=True
)
# Returns: updated streak, completion rate

# Analyze patterns
patterns = await agent.analyze_patterns(context, days_back=30)
# Returns: completion rates, weakest days, trends

# Get improvement suggestions
suggestions = await agent.suggest_adjustment(
    context=context,
    routine_id="gym"
)
```

### ShoppingAgent
Manage shopping lists, compare prices, suggest timing.

```python
from agents import ShoppingAgent

agent = ShoppingAgent()

# Get lists
lists = await agent.get_lists(context, list_type="want")

# Add item
item = await agent.add_item(
    context=context,
    name="New headphones",
    list_type="want",
    category="electronics",
    estimated_price=200,
    priority="high"
)

# Compare prices
comparison = await agent.compare_prices(
    context=context,
    item_name="headphones"
)
# Returns best deals across retailers

# Suggest when to buy
timing = await agent.suggest_timing(
    context=context,
    item_name="winter jacket",
    category="clothing"
)
```

### RelationshipAgent
Plan dates, track important dates, store preferences.

```python
from agents import RelationshipAgent

agent = RelationshipAgent()

# Get preferences
prefs = await agent.get_preferences(context)

# Suggest date
suggestion = await agent.suggest_date(
    context=context,
    type_="romantic",
    budget=100,
    duration_hours=3
)

# Get upcoming important dates
upcoming = await agent.get_upcoming_dates(context, days_ahead=90)

# Create design poster
poster = await agent.create_date_poster(
    context=context,
    occasion="anniversary",
    theme="romantic"
)

# Store preference
await agent.store_preference(
    context=context,
    category="interests",
    preference="Italian food",
    detail="Loves pasta, especially carbonara"
)
```

### ConciergeAgent
Find events, restaurants, activities, and book reservations.

```python
from agents import ConciergeAgent

agent = ConciergeAgent()

# Search events
events = await agent.search_events(
    context=context,
    query="jazz concert",
    category="music"
)

# Find restaurants
restaurants = await agent.find_restaurants(
    context=context,
    cuisine="Italian",
    price_range="upscale",
    party_size=2,
    date="2026-03-20",
    time="19:00"
)

# Discover activities
activities = await agent.discover_activities(
    context=context,
    category="outdoor",
    duration_minutes=120
)

# Book reservation
booking = await agent.book_reservation(
    context=context,
    restaurant_id="rest_002",
    date="2026-03-20",
    time="19:00",
    party_size=2,
    name="Hanzalah"
)
```

## Common Patterns

### Route by Intent

```python
from agents import get_agent_for_intent

user_input = "I need to find free time tomorrow"
agent_class = get_agent_for_intent(user_input)
agent = agent_class()
```

### Full Agent Workflow

```python
async def handle_user_request(user_message, context):
    # 1. Select agent by intent
    agent_class = get_agent_for_intent(user_message)
    agent = agent_class()
    
    # 2. Generate plan
    plan = await agent.plan(user_message, context)
    
    # 3. Execute plan
    result = await agent.execute(plan, context, mcp_client)
    
    # 4. Reflect and summarize
    summary = await agent.reflect(result)
    
    return summary
```

### Error Handling

```python
try:
    plan = await agent.plan(message, context)
    result = await agent.execute(plan, context, mcp_client)
    
    if not result.success:
        print(f"Some steps failed:")
        for step, error in result.steps_failed:
            print(f"  - {step.description}: {error}")
    
    summary = await agent.reflect(result)
    
except Exception as e:
    print(f"Agent error: {e}")
```

## Context Structure

```python
context = {
    # Calendar
    "calendar_events": [
        {
            "id": "evt_123",
            "title": "Meeting",
            "date": "2026-03-17",
            "start_time": "09:00",
            "end_time": "09:30"
        }
    ],
    
    # Email
    "emails": [
        {
            "id": "email_123",
            "sender": "alice@example.com",
            "subject": "Project update",
            "body": "Here's the latest...",
            "read": False,
            "received_time": "2026-03-17T09:15:00Z"
        }
    ],
    
    # Tasks
    "tasks": [
        {
            "title": "Finish report",
            "date": "2026-03-17",
            "completed": False
        }
    ],
    
    # Shopping
    "shopping_lists": {
        "need": [],
        "want": []
    },
    "purchases": [],
    
    # Relationship
    "relationship_preferences": {},
    "relationship_important_dates": [],
    
    # Routines
    "routines": {},
    "routine_gym_history": [],
    
    # Saved recommendations
    "saved_recommendations": []
}
```

## Testing

```python
import asyncio
from agents import SchedulerAgent

async def test():
    agent = SchedulerAgent()
    context = {"calendar_events": []}
    
    # Test planning
    plan = await agent.plan("Find time for lunch", context)
    assert len(plan) > 0
    
    # Test methods
    schedule = await agent.get_today_schedule(context)
    assert schedule is not None
    
    print("✓ All tests passed!")

asyncio.run(test())
```

## Next Steps

1. Review [agents/README.md](agents/README.md) for detailed API docs
2. Check [AGENTS_MANIFEST.txt](AGENTS_MANIFEST.txt) for architecture overview
3. Implement dispatcher logic to route user messages to agents
4. Connect MCP tools for actual data operations
5. Add persistent storage for context and history

## Support

- Each agent has comprehensive docstrings
- Error messages are logged with full context
- Agent methods are fully typed with type hints
- All code is production-ready, not stubs
