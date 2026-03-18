# Quick Reference - Memory Layer & MCP Client

## File Locations

```
personal-agent/
├── memory/
│   ├── __init__.py          # MemoryStore export
│   ├── store.py             # MemoryStore implementation (952 lines)
│   └── schema.sql           # PostgreSQL schema (186 lines)
└── mcp/
    ├── __init__.py          # MCPClient export
    ├── client.py            # MCPClient implementation (401 lines)
    └── servers.json         # MCP server configuration
```

## Memory Store Methods

### Initialization
```python
store = MemoryStore(dsn="postgresql://...", min_size=2, max_size=10)
await store.init()      # Create pool & schema
await store.close()     # Close pool
```

### Conversations
```python
await store.save_conversation(user_id, agent, message, role, metadata=None)
history = await store.get_conversation_history(user_id, agent=None, limit=20)
```

### Memories
```python
memory_id = await store.save_memory(
    user_id, category, key, value, source_agent,
    embedding=None, confidence=1.0, expires_at=None
)
memories = await store.get_memories(user_id, category=None, limit=50)
results = await store.search_memories(user_id, query_embedding, top_k=5)
```

Categories: `fact`, `preference`, `event`, `relationship`, `routine`, `shopping`

### Plans
```python
plan_id = await store.save_plan(user_id, agent, steps)
await store.update_plan_status(plan_id, status)
plans = await store.get_active_plans(user_id)
```

Statuses: `pending`, `approved`, `executing`, `completed`, `failed`, `cancelled`

### Routines
```python
routine_id = await store.upsert_routine(user_id, name, schedule, metadata=None)
await store.complete_routine(user_id, routine_name)
routines = await store.get_routines(user_id)
```

Schedule examples: `"daily"`, `"0 9 * * 1-5"` (cron format)

### Shopping
```python
item_id = await store.add_shopping_item(
    user_id, name, category=None, priority="want",
    price_target=None, url=None, notes=None
)
items = await store.get_shopping_list(user_id, status="active")
```

Status: `active`, `purchased`, `archived`
Priority: `need`, `want`

### Relationships
```python
event_id = await store.save_relationship_event(
    user_id, event_type, title, description=None,
    date=None, metadata=None
)
events = await store.get_relationship_events(user_id, event_type=None)
```

Event types: `date`, `anniversary`, `gift`, `note`

### Context
```python
context = await store.get_context_for_agent(
    user_id, agent_name,
    num_conversations=10, num_memories=20
)
# Returns: {"recent_conversations": [...], "memories": [...]}
```

## MCP Client Methods

### Initialization
```python
client = MCPClient(servers_config_path="mcp/servers.json", timeout=30)
```

### Server Management
```python
await client.connect(server_name)
await client.disconnect(server_name)
await client.close_all()

tools = await client.list_tools(server_name)
```

### Tool Calling
```python
result = await client.call_tool(
    server_name, tool_name, arguments, timeout=None
)
```

### Tool Registry
```python
tools = client.get_tools_for_agent(agent_name)
# Returns: {server_name: [tool_names]}
```

Agents: `scheduler`, `inbox`, `routine`, `shopping`, `relationship`, `concierge`
Servers: `gcal`, `gmail`, `brave_search`, `canva`, `memory`

## Agent-Server Mapping

| Agent | Servers |
|-------|---------|
| scheduler | gcal |
| inbox | gmail |
| routine | gcal, memory |
| shopping | brave_search, memory |
| relationship | canva, brave_search, memory |
| concierge | brave_search, gcal |

## Type Hints

```python
# Memory categories
category: Literal["fact", "preference", "event", "relationship", "routine", "shopping"]

# Conversation roles
role: Literal["user", "assistant", "system"]

# Plan status
status: Literal["pending", "approved", "executing", "completed", "failed", "cancelled"]

# Shopping priority
priority: Literal["need", "want"]

# Shopping status
status: Literal["active", "purchased", "archived"]

# Relationship event type
event_type: Literal["date", "anniversary", "gift", "note"]

# Agent names
agent: Literal["scheduler", "inbox", "routine", "shopping", "relationship", "concierge"]

# MCP servers
server: Literal["gcal", "gmail", "brave_search", "canva", "memory"]
```

## Database Schema

### conversations
- id, user_id, agent_name, message, role, metadata, created_at
- Indexes: user_id, agent_name, created_at, (user_id, agent_name, created_at)

### memories
- id, user_id, category, key, value, embedding, confidence, source_agent, created_at, updated_at, expires_at
- Indexes: user_id, category, created_at, (user_id, category), expires_at, **embedding (ivfflat)**

### plans
- id, user_id, agent_name, plan_steps (jsonb), status, created_at, updated_at, approved_at, completed_at
- Indexes: user_id, status, created_at, (user_id, status)

### routines
- id, user_id, name, schedule, last_completed, streak, total_completions, metadata, created_at, updated_at
- Indexes: user_id, created_at
- Constraint: (user_id, name) UNIQUE

### shopping_items
- id, user_id, name, category, priority, price_target, url, notes, status, created_at, updated_at
- Indexes: user_id, status, priority, created_at

### relationship_events
- id, user_id, event_type, title, description, date, metadata, created_at, updated_at
- Indexes: user_id, event_type, date, created_at

## Common Patterns

### Get Recent Activity
```python
history = await store.get_conversation_history(user_id, agent="scheduler", limit=10)
```

### Save with Embedding
```python
import numpy as np
embedding = np.random.randn(1536).tolist()
await store.save_memory(
    user_id, "preference", "color", "blue",
    source_agent="ui", embedding=embedding
)
```

### Search Similar Memories
```python
query = np.random.randn(1536).tolist()
similar = await store.search_memories(user_id, query, top_k=5)
```

### Track Routine Streak
```python
await store.complete_routine(user_id, "Morning Standup")
routines = await store.get_routines(user_id)
morning = [r for r in routines if r['name'] == "Morning Standup"][0]
print(f"Streak: {morning['streak']} days")
```

### Create and Approve Plan
```python
plan_id = await store.save_plan(
    user_id, "scheduler",
    [
        {"step": 1, "action": "create_event"},
        {"step": 2, "action": "send_notification"}
    ]
)
await store.update_plan_status(plan_id, "approved")
await store.update_plan_status(plan_id, "executing")
await store.update_plan_status(plan_id, "completed")
```

### Manage Shopping List
```python
# Add item
item_id = await store.add_shopping_item(
    user_id, "Mechanical Keyboard",
    category="electronics", priority="want", price_target=120.00
)

# Get active list
items = await store.get_shopping_list(user_id, status="active")

# Get purchased items
purchased = await store.get_shopping_list(user_id, status="purchased")
```

### Save Relationship Event
```python
await store.save_relationship_event(
    user_id, "anniversary",
    title="Sarah's Birthday",
    date=datetime(2026, 5, 15),
    metadata={
        "person_name": "Sarah",
        "relationship": "friend",
        "reminder_days": 7,
        "gift_ideas": ["Book", "Coffee"]
    }
)

events = await store.get_relationship_events(
    user_id, event_type="anniversary"
)
```

### Call MCP Tool
```python
result = await client.call_tool(
    "gcal",
    "create_event",
    {
        "title": "Team Standup",
        "start_time": "2026-03-18T09:00:00Z",
        "duration_minutes": 30
    }
)
```

## Configuration

### Memory Store DSN
```
postgresql://username:password@localhost:5432/personal_agent
```

### MCP servers.json
```json
{
  "gcal": {
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-google-calendar"],
    "env": {"GOOGLE_CREDENTIALS_PATH": "/app/credentials/google.json"}
  }
}
```

### Environment Variables
```bash
export DATABASE_URL="postgresql://localhost/agent"
export BRAVE_SEARCH_API_KEY="your-key"
export CANVA_API_KEY="your-key"
export GOOGLE_CREDENTIALS_PATH="/app/credentials/google.json"
```

## Error Handling

All errors are logged with context:

```python
try:
    await store.save_memory(user_id, category, key, value, agent)
except Exception as e:
    # Logs: "save_memory_failed", user_id, category, error
    # Handle error gracefully
```

## Performance Tips

1. **Use get_context_for_agent()** to get relevant data for agents
2. **Batch operations** when loading multiple items (not yet implemented, extensible)
3. **Vector search** for semantic relationships in memories
4. **Index on metadata** if querying specific JSON fields
5. **Pagination** with `limit` parameter for large result sets

## Testing Setup

```python
import asyncio
from memory import MemoryStore
from uuid import uuid4

async def test():
    store = MemoryStore("postgresql://localhost/test_agent")
    await store.init()

    user_id = uuid4()
    await store.save_conversation(
        user_id, "test", "hello", "user"
    )

    history = await store.get_conversation_history(user_id)
    assert len(history) == 1

    await store.close()

asyncio.run(test())
```

## Debugging

Enable structured logging:

```python
import structlog
import logging

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.logging.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Now all logs will include context automatically
```

## Cleanup

Always close resources:

```python
# Memory store
await store.close()

# MCP client
await client.close_all()

# In async context manager (recommended)
async with store.pool as pool:
    # Use pool
    pass
```

## Status Codes

No HTTP-style codes - exceptions raised with meaningful messages. Always check logs.

## Limits

- **Conversation history**: No limit (paginate with `limit` parameter)
- **Memory embeddings**: 1536 dimensions (OpenAI compatible)
- **Confidence scores**: 0.0 to 1.0
- **Vector search**: Top-K up to available records
- **Tool timeout**: 30 seconds (configurable)
- **Connection pool**: Min 2, Max 10 (configurable)
