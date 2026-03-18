# Personal AI Agent System - Agents Module

## Overview

This module contains a complete multi-agent system for personal task automation. Each agent is a specialized worker that handles a specific domain.

## Architecture

### Base Agent (`base.py`)

All agents inherit from `BaseAgent` which provides:

- **Planning**: Uses Claude to generate step-by-step plans
- **Execution**: Executes plans via MCP tool calls with retry logic
- **Reflection**: Reviews results and generates summaries
- **Error Handling**: Built-in retry logic (max 2 retries per step)
- **Logging**: Structured logging with agent context

Key classes:
- `BaseAgent`: Abstract base class
- `PlanStep`: Represents a single action in a plan
- `ExecutionResult`: Result from executing a plan
- `ActionType`: Enum of action types

### Specialized Agents

#### SchedulerAgent (`scheduler.py`)
**Purpose**: Calendar management and time optimization

Capabilities:
- Read and understand calendar availability
- Find optimal free time slots (respects workday hours 9am-5pm)
- Suggest scheduling based on task type and priority
- Create calendar events with attendee management
- Provide morning briefings and end-of-day reviews
- Check task completion status

Key methods:
- `get_today_schedule()`: Get today's events
- `find_free_slots()`: Find available time windows
- `suggest_time()`: Get optimal time for a task
- `create_event()`: Schedule new calendar event
- `provide_morning_briefing()`: Generate daily briefing
- `end_of_day_review()`: Summary of the day

Scoring: Prioritizes early mornings (9am-12pm) for deep work, adjusts for task type and priority.

#### InboxAgent (`inbox.py`)
**Purpose**: Email triage and communication management

Capabilities:
- Read and search emails
- Prioritize by urgency (urgent/important/action/fyi/spam)
- Summarize long emails concisely
- Extract action items and deadlines
- Draft professional replies in multiple styles
- Mark emails as read

Prioritization logic:
- **URGENT**: Contains urgent keywords, deadline within 24h
- **IMPORTANT**: From known important contacts, work-related
- **ACTION_REQUIRED**: Needs response, personal matters
- **FYI**: Informational only
- **SPAM**: Promotional or low-value

Key methods:
- `get_unread_emails()`: Fetch unread messages
- `search_emails()`: Search by query
- `prioritize_emails()`: Categorize by urgency
- `summarize_email()`: Extract key points
- `draft_reply()`: Generate reply suggestions
- `find_action_items()`: Extract all action items

#### RoutineAgent (`routine.py`)
**Purpose**: Habit tracking and routine optimization

Capabilities:
- Track daily routine completion
- Analyze patterns by day of week
- Identify blockers preventing completion
- Suggest adjustments for improvement
- Provide motivation and celebrate streaks
- Generate insights from 30+ days of data

Key methods:
- `get_routines()`: List all tracked routines
- `check_completion()`: Log routine completion
- `analyze_patterns()`: Find trends and weak days
- `suggest_adjustment()`: Get improvement suggestions
- `identify_blockers()`: Find barriers to completion
- `send_reminder()`: Generate context-aware reminders

Insights: Celebrates streaks (7-day, 30-day), tracks completion rate, identifies weakest days.

#### ShoppingAgent (`shopping.py`)
**Purpose**: Smart shopping and purchase decisions

Capabilities:
- Manage want vs. need lists
- Search for items and get pricing estimates
- Compare prices across retailers
- Suggest optimal buying times by category
- Track spending by category
- Provide budget analysis

Categories: Groceries, Electronics, Clothing, Home, Fitness, Entertainment

Timing logic:
- **Groceries**: Weekly (Tuesdays/Wednesdays) - 10-20% discount
- **Electronics**: Black Friday, new releases - 20-40% discount
- **Clothing**: End of season - 30-70% discount
- **Home**: Weekend sales - 15-25% discount
- **Fitness**: January, summer - 20-30% discount

Key methods:
- `get_lists()`: View need/want lists
- `add_item()`: Add with auto-wait recommendation
- `remove_item()`: Mark completed
- `search_item()`: Get pricing and recommendations
- `compare_prices()`: Find best deals
- `suggest_timing()`: When to buy
- `track_spending()`: Monitor by category

#### RelationshipAgent (`relationship.py`)
**Purpose**: Relationship nurturing and date planning

Capabilities:
- Store and recall relationship preferences
- Suggest personalized date ideas
- Track important dates and anniversaries
- Create romantic content (Canva integration)
- Provide thoughtful reminders
- Analyze relationship patterns

Date categories:
- **Casual**: Coffee, walk, cooking (low-key)
- **Romantic**: Sunset dinner, candlelit picnic (special)
- **Active**: Hiking, sports, climbing (energetic)
- **Experiential**: Classes, shows, wine tasting (memorable)

Key methods:
- `get_preferences()`: Retrieve stored preferences
- `suggest_date()`: Get personalized date ideas
- `get_upcoming_dates()`: See important dates ahead
- `create_date_poster()`: Generate Canva design
- `track_important_date()`: Add anniversary/birthday
- `store_preference()`: Remember details about girlfriend

Personalization: Scores suggestions based on interests, considers budget and duration.

#### ConciergeAgent (`concierge.py`)
**Purpose**: Local discovery and booking logistics

Capabilities:
- Search for events and concerts
- Find restaurants with availability
- Discover activities and experiences
- Save recommendations for later
- Handle booking confirmations
- Search the web for suggestions

Query types:
- Events: Music, art, food, entertainment
- Restaurants: Filtered by cuisine, price range
- Activities: Fitness, creative, outdoor, wellness

Key methods:
- `search_events()`: Find upcoming events
- `find_restaurants()`: Search with availability check
- `discover_activities()`: Find things to do
- `save_recommendation()`: Store for later
- `book_reservation()`: Confirm restaurant booking
- `search_web()`: General web search

## Agent Registry

The `__init__.py` file exports:

- `AGENT_REGISTRY`: Maps intent keywords to agent classes
- `get_agent_for_intent()`: Route tasks to appropriate agent
- `get_all_agents()`: List all available agents

### Intent Routing

```python
from agents import get_agent_for_intent

intent = "schedule a meeting"
agent_class = get_agent_for_intent(intent)  # Returns SchedulerAgent
```

## Usage Pattern

### 1. Create Agent Instance
```python
from agents import SchedulerAgent

agent = SchedulerAgent()
```

### 2. Generate Plan
```python
plan = await agent.plan(
    message="Find time for a 1-hour meeting with Sarah",
    context={
        "calendar_events": [
            {"title": "Standup", "date": "2026-03-17", "start_time": "09:00", "end_time": "09:30"}
        ]
    }
)
```

### 3. Execute Plan
```python
result = await agent.execute(
    plan=plan,
    context=context,
    mcp_client=mcp_client
)
```

### 4. Reflect on Results
```python
summary = await agent.reflect(result)
print(summary)
```

## Data Structures

### PlanStep
```python
@dataclass
class PlanStep:
    step_number: int
    action: str  # e.g., "fetch_emails", "search_items"
    tool: Optional[str]  # e.g., "gmail.search_messages"
    parameters: Dict[str, Any]  # Tool-specific parameters
    description: str  # Human-readable description
```

### ExecutionResult
```python
@dataclass
class ExecutionResult:
    success: bool
    steps_completed: List[PlanStep]
    steps_failed: List[tuple[PlanStep, str]]
    summary: str
    data: Dict[str, Any]  # Results from tool calls
```

## MCP Tool References

Agents reference MCP tools in format: `service.method`

Examples:
- `gcal.list_events`: Get calendar events
- `gcal.create_event`: Create calendar event
- `gmail.search_messages`: Search emails
- `gmail.create_draft`: Draft email
- `canva.generate_design`: Create design
- `brave.search`: Web search

## Error Handling

All agents implement:
- **Automatic Retries**: Max 2 retries per step with exponential backoff
- **Structured Logging**: All actions logged with agent context
- **Graceful Degradation**: Partial success returns completed steps + failed steps
- **User-Friendly Summaries**: Results summarized with next steps

## Configuration

Each agent has customizable parameters:

### SchedulerAgent
- Workday hours (default: 9am-5pm)
- Buffer time between meetings (default: 15min)
- Focus time blocks

### InboxAgent
- Urgent keywords
- Work keywords
- Response triggers

### RoutineAgent
- Default routines
- Streak thresholds for celebrations
- Completion rate targets

### ShoppingAgent
- Budget limits
- Category preferences
- Price alert thresholds

### RelationshipAgent
- Interest categories
- Date budget limits
- Reminder timing

### ConciergeAgent
- Radius for local search
- Cuisine preferences
- Activity types

## Testing

All classes use type hints and async/await. To test:

```python
import asyncio
from agents import SchedulerAgent

async def test():
    agent = SchedulerAgent()
    context = {
        "calendar_events": [],
        "tasks": [],
    }
    plan = await agent.plan("Find time for lunch", context)
    assert plan is not None
    assert len(plan) > 0

asyncio.run(test())
```

## Production Notes

- All code is production-ready with error handling
- Uses `structlog` for structured logging
- Implements async/await for concurrency
- No stub methods - all methods have real implementation
- Type hints on all public methods
- Comprehensive docstrings with examples
