# Personal AI Agent - Architecture & Implementation

## Overview

This is a production-ready multi-agent personal AI assistant system:
- **Interface**: Telegram bot with user whitelist and rate limiting
- **Orchestration**: LangGraph state machine for intelligent routing
- **LLM**: Claude API (Anthropic) with specialized agents
- **Storage**: Redis for rate limiting and session state
- **Security**: Input sanitization, prompt injection detection, comprehensive logging

## Core Components

### 1. Bot Layer (`bot/`)

#### `bot/security.py` - Security & Authentication

**Classes:**

- **`UserAuth`**: Validates Telegram user IDs against whitelist
  - O(1) lookup using set membership
  - Configurable whitelist from environment
  - Logs all auth attempts

- **`RateLimiter`**: Per-user rate limiting with Redis
  - Sliding window algorithm (60-second window)
  - Configurable limit per minute
  - Automatic cleanup of expired entries
  - Fails open (allows on error) with logging

- **`InputSanitizer`**: Detects prompt injection and abuse
  - 9 injection patterns (regex-based)
  - Length validation
  - Null byte detection
  - Special character ratio checking
  
- **`security_check()` function**: Orchestrates all checks in sequence
  - Returns early on first failure
  - Detailed logging for investigation
  - Generic error messages to users

- **`@secured` decorator**: Wraps handlers with security checks
  - Extracts user_id from context
  - Runs security_check before handler execution
  - Prevents unauthorized/unsafe messages from processing

**Injection Patterns Detected:**
```
- "ignore previous instructions"
- "system:" prefixes
- "forget everything"
- Role changes ("act as", "pretend", "imagine you are")
- "new instructions", "new system"
- Character encoding escapes
```

#### `bot/handlers.py` - Message Handlers

**Functions:**

- **`handle_start()`**: /start command
  - Welcome message explaining bot capabilities
  - Lists all 7 intent categories
  - Friendly emoji formatting

- **`handle_message()`**: Text message processing
  - Shows typing indicator
  - Runs security checks (via middleware)
  - Dispatches to LangGraph
  - Shows plan with approval buttons if needed
  - Manages conversation history

- **`handle_callback()`**: Inline keyboard responses
  - Approves, rejects, or edits plans
  - Executes on approval
  - Cleans up pending state
  - Full error handling

**UI Elements:**
- Inline keyboard buttons: ✅ Approve, ✏️ Edit, ❌ Cancel
- Typing indicator during processing
- Markdown formatting for clean messages
- Emoji for visual clarity

#### `bot/main.py` - Telegram Application

**TelegramBotApp class:**

- **Initialization**: Validates config, sets up security, registers handlers
- **Handler registration**: Commands, messages, callbacks
- **Middleware**: Injects security components into context, pre-checks user auth
- **Lifecycle**: Startup validation, graceful shutdown
- **Dual modes**:
  - **Polling** (development): Continuously polls Telegram servers
  - **Webhook** (production): Receives updates via HTTPS

**Key Features:**
- Config validation at startup
- Async throughout (no blocking)
- Proper error handling and logging
- Graceful shutdown with resource cleanup

### 2. Dispatcher Layer (`dispatcher/`)

#### `dispatcher/router.py` - Intent Classification

**Function: `classify_intent(message, conversation_history)`**

- Uses Claude Haiku for speed and cost
- Classifies into 7 intents (see below)
- Returns intent + confidence score (0-1)
- Asks for clarification if confidence < 0.7
- Includes conversation context for better classification

**Intent Categories:**
1. **scheduling** - Calendar, meetings, time management
2. **email** - Composing, sending emails
3. **routine** - Daily tasks, habits, checklists
4. **shopping** - Lists, product research
5. **relationship** - Social coordination, messaging
6. **concierge** - Research, bookings, reservations
7. **general_chat** - Casual conversation

#### `dispatcher/planner.py` - Plan Generation

**Function: `generate_plan(message, intent, history)`**

- Uses Claude Sonnet for capability and reasoning
- Generates numbered action steps
- Maximum 7 steps per plan
- Each step 1-2 sentences max
- Returns estimated duration and approval requirement

**Safety Validation:**
- Removes dangerous patterns (rm -rf, delete database, etc.)
- Caps step length at 200 characters
- Validates plan isn't empty
- Checks for single-step requests

**Approval Logic:**
- Multi-step plans always require approval
- Single steps with state modifications require approval
- Read-only operations skip approval

#### `dispatcher/graph.py` - LangGraph State Machine

**State (TypedDict):**
```python
{
    "message": str,              # User input
    "user_id": int,              # Telegram ID
    "intent": str,               # Classified intent
    "intent_confidence": float,   # 0.0-1.0
    "selected_agent": str,       # Agent name
    "plan": list[str],           # Action steps
    "approval_status": str,      # pending_approval, approved, etc.
    "result": str,               # Final response
    "memory_context": str,       # User context
    "conversation_history": list[dict],
    "error": Optional[str],
}
```

**Nodes:**

1. **classify_intent_node()**
   - Calls `classify_intent()` from router
   - Sets intent and confidence
   - Checks if clarification needed
   - May transition to "needs_clarification" status

2. **route_to_agent_node()**
   - Maps intent to agent
   - Selects appropriate system prompt
   - Updates selected_agent in state

3. **generate_plan_node()**
   - Calls `generate_plan()` from planner
   - Validates plan
   - Determines if approval needed
   - Sets approval_status

4. **await_approval_node()**
   - Marks waiting for user response
   - Callback handler updates state asynchronously
   - No actual waiting in graph execution

5. **execute_plan_node()**
   - Uses agent's system prompt
   - Calls Claude Sonnet with plan
   - Returns execution result
   - Sets approval_status to "completed"

6. **format_response_node()**
   - Ensures result is set
   - Cleans up state for user display
   - Final node before END

**Edges & Routing:**
```
classify_intent
    ↓
route_to_agent
    ↓
generate_plan
    ├─ if error → format_response
    ├─ if needs_clarification → format_response
    ├─ if multi-step → await_approval
    └─ if single-step → execute_plan
        ↓
    (await_approval)
        ├─ approved (callback) → execute_plan
        ├─ rejected (callback) → format_response
        └─ edit (callback) → generate_plan (loop)
        ↓
    execute_plan
        ↓
    format_response
        ↓
    END
```

**Agent System Prompts:**

Each intent maps to specialized agent with custom system prompt:
- Scheduling agent: Calendar/time expertise
- Email agent: Professional communication
- Routine agent: Productivity focus
- Shopping agent: Budget-conscious recommendations
- Relationship agent: Social intelligence
- Concierge agent: General problem-solving
- General chat: Friendly conversationalist

### 3. Configuration (`config/settings.py`)

**Settings Classes:**

- **TelegramConfig**: Bot token, whitelist, webhook mode
- **WebhookConfig**: Domain, URL, port
- **RedisConfig**: Connection URL, database number
- **AnthropicConfig**: API key, model selection
- **SecurityConfig**: Rate limits, input length, log level

**Environment Variables:**
```bash
# Required
TELEGRAM_BOT_TOKEN
TELEGRAM_USER_WHITELIST

# Optional (with defaults)
REDIS_URL=redis://localhost:6379
RATE_LIMIT_PER_MINUTE=10
MAX_INPUT_LENGTH=2000
LOG_LEVEL=INFO
USE_WEBHOOK=false
```

## Data Flow

```
User → Telegram
    ↓
Middleware (security check)
    ├─ UserAuth check
    ├─ RateLimit check
    └─ InputSanitizer check
    ↓
handle_message()
    ↓
dispatch_message() → dispatcher_graph.ainvoke()
    ├─ classify_intent_node()
    ├─ route_to_agent_node()
    ├─ generate_plan_node()
    ├─ await_approval_node()
    │   ├─ User presses button
    │   └─ Callback updates state
    ├─ execute_plan_node()
    └─ format_response_node()
    ↓
Result to User via Telegram
    ↓
Update conversation_history
```

## Security Implementation

### Defense Layers

1. **User Authorization (Layer 1)**
   - Whitelist check before any processing
   - Fast O(1) lookup
   - Logged per-request

2. **Rate Limiting (Layer 2)**
   - Per-user limit (default 10/min)
   - Redis-backed sliding window
   - Automatic cleanup
   - Fails open with logging

3. **Input Validation (Layer 3)**
   - Prompt injection detection
   - Length validation (default 2000 chars)
   - Null byte detection
   - Special character ratio checks

4. **Error Handling (Layer 4)**
   - No error details to users
   - All errors structured-logged
   - User IDs included for investigation
   - Graceful fallbacks

### Logging

All events logged with structlog:
```python
logger.info("event_name", user_id=123, context="value")
logger.error("error_event", error=str(e), user_id=123)
logger.warning("suspicious_pattern", pattern="...", user_id=123)
```

Logs include:
- Auth attempts (success/failure)
- Rate limit violations
- Injection pattern matches
- Intent classifications
- Plan generation
- Execution results
- All errors with context

## Performance Characteristics

### Latency

- Intent classification: ~500ms (Haiku)
- Plan generation: ~1-2s (Sonnet)
- Plan execution: ~1-3s (Sonnet)
- Total request: ~3-6 seconds

### Throughput

With 1 Redis instance:
- Rate limiting: ~10,000 checks/sec
- Bot instances: Scale horizontally
- Claude API: Limited by quota (typically 100k TPM)

### Resource Usage

- Memory: ~200MB base + ~50MB per concurrent user
- Redis: ~1KB per rate-limit tracking per user
- Storage: Minimal (stateless)

## Testing

Tests in `tests/`:

- **test_security.py**: UserAuth, RateLimiter, InputSanitizer
- **test_router.py**: Intent classification
- Plan generation and validation
- State machine execution

Run with:
```bash
pytest -v
pytest --cov=.
```

## Deployment

### Development (Polling)
```bash
python -m bot.main
```

### Production (Webhook)
```bash
docker-compose up -d
# or
systemctl start personal-agent
```

See DEPLOYMENT.md for full instructions.

## Extensibility

### Adding New Intents

1. Add to intent list in `dispatcher/router.py`
2. Add SYSTEM prompt in `dispatcher/graph.py`
3. Add mapping in `route_to_agent_node()`
4. Update documentation

### Adding New Security Patterns

1. Add regex pattern to `InputSanitizer.INJECTION_PATTERNS`
2. Patterns are case-insensitive and compiled on init
3. Test with new inputs

### Custom Agents

Agents are defined by system prompts. To add custom logic:

1. Extend `execute_plan_node()` with agent-specific logic
2. Call external APIs if needed (async supported)
3. Return formatted result string

## Files Reference

**Bot Layer:**
- `/bot/__init__.py` - Package marker (empty)
- `/bot/main.py` - Application setup (560 lines)
- `/bot/handlers.py` - Message handlers (340 lines)
- `/bot/security.py` - Security classes (400 lines)

**Dispatcher Layer:**
- `/dispatcher/__init__.py` - Package marker (empty)
- `/dispatcher/graph.py` - LangGraph state machine (550 lines)
- `/dispatcher/router.py` - Intent classification (180 lines)
- `/dispatcher/planner.py` - Plan generation (250 lines)

**Configuration:**
- `/config/settings.py` - Settings management (160 lines)

**Supporting Files:**
- `/requirements.txt` - Dependencies
- `/README.md` - User guide
- `/DEPLOYMENT.md` - Deployment guide
- `/ARCHITECTURE.md` - This file
- `/__main__.py` - Entry point
- `/tests/` - Unit tests

**Total:** ~2,800 lines of production code

## Error Handling Strategy

All errors follow this pattern:

```python
try:
    result = await operation()
except SpecificError as e:
    logger.error("operation_failed", user_id=user_id, error=str(e))
    await send_to_user("Generic error message")
except Exception as e:
    logger.error("unexpected_error", error=str(e), traceback=...)
    await send_to_user("Something went wrong")
```

Users never see internal errors. Logs capture:
- Error type and message
- User ID for debugging
- Stack trace if unexpected
- Context (what operation failed)

## Next Steps

1. Set up environment variables
2. Configure Telegram bot token
3. Start Redis
4. Run tests: `pytest -v`
5. Start bot: `python -m bot.main`

See README.md and DEPLOYMENT.md for detailed instructions.
