# 🤖 personal-agent

A self-hosted personal AI assistant that runs 24/7 on your VPS and talks to you through Telegram. Built around a fleet of specialised agents — each one owns a domain of your life — coordinated by a central dispatcher that plans before it acts.

> Built for one person. Extensible by design. You're the only one who can talk to it.

---

## What it does

You send a message on Telegram. The dispatcher figures out which agent to hand it to, that agent drafts a step-by-step plan, sends it back to you for approval, and only then executes. Nothing happens behind your back.

| Agent | What it handles |
|---|---|
| 📅 **Scheduler** | Reads your Google Calendar, finds free slots, suggests when to do things, follows up on tasks |
| 📧 **Inbox Manager** | Summarises Gmail, ranks emails by urgency, drafts replies for you to approve |
| 🎯 **Routine Coach** | Tracks your habits, notices patterns, sends nudges at the right time |
| 🛒 **Shopping Brain** | Manages your want/need lists, tracks prices, suggests when to buy |
| ❤️ **Relationship Keeper** | Remembers preferences, suggests dates, tracks important dates, builds Canva posters |
| 🎉 **Concierge** | Finds events and restaurants, saves recommendations, handles bookings |

---

## Architecture

```
Telegram (your interface)
    │
    ▼
Dispatcher / Orchestrator  ◄──── PostgreSQL + pgvector (long-term memory)
    │
    ├── Intent classification (Claude Haiku — fast + cheap)
    ├── Agent routing
    ├── Plan generation  ──► Plan sent to Telegram for your approval
    │                             ✅ Approve / ✏️ Edit / ❌ Cancel
    └── Execution via MCP tools
          ├── Google Calendar MCP
          ├── Gmail MCP
          ├── Brave Search MCP
          ├── Canva MCP
          └── Memory MCP (internal)
```

### Plan-Before-Execute

Every non-trivial action goes through a review step. The agent tells you exactly what it's going to do before doing it:

```
🤖 Here's my plan:
  1. Check your calendar for free slots Thursday–Sunday
  2. Cross-reference with your girlfriend's saved preferences
  3. Search for rooftop restaurants in your area
  4. Draft a booking message for the top result

✅ Approve   ✏️ Edit   ❌ Cancel
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM | Anthropic Claude (Haiku for routing, Sonnet for planning/execution) |
| Orchestration | LangGraph |
| Bot interface | python-telegram-bot |
| Tool protocol | MCP (Model Context Protocol) |
| Memory | PostgreSQL 16 + pgvector |
| Cache / rate limiting | Redis 7 |
| Infrastructure | Docker Compose |

---

## Project structure

```
personal-agent/
├── bot/                    # Telegram bot + security layer
│   ├── main.py             # Entry point, webhook setup
│   ├── security.py         # User whitelist, rate limiting, injection detection
│   └── handlers.py         # Message + callback handlers
├── dispatcher/             # LangGraph orchestrator
│   ├── graph.py            # State graph definition
│   ├── router.py           # Intent classification
│   └── planner.py          # Plan generation + validation
├── agents/                 # Specialist agents
│   ├── base.py             # Abstract base class (plan → execute → reflect)
│   ├── scheduler.py
│   ├── inbox.py
│   ├── routine.py
│   ├── shopping.py
│   ├── relationship.py
│   └── concierge.py
├── mcp/                    # MCP client + server configs
│   ├── client.py
│   └── servers.json
├── memory/                 # PostgreSQL store
│   ├── store.py
│   └── schema.sql
├── config/                 # Pydantic settings
│   └── settings.py
└── docker-compose.yml
```

---

## Security

- **Telegram whitelist** — only your user ID can interact with the bot. Every message is checked.
- **Rate limiting** — Redis-backed sliding window (configurable, default 20 msg/min)
- **Prompt injection detection** — common injection patterns are caught and blocked before reaching the LLM
- **SQL injection prevention** — parameterised queries throughout, no string interpolation
- **Secrets management** — all credentials via `.env`, never committed
- **Network isolation** — Docker internal network, only the bot container is externally reachable

---

## Quick start

See [DEPLOYMENT.md](DEPLOYMENT.md) for full setup instructions.

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_USERNAME/personal-agent
cd personal-agent
cp .env.example .env
# Fill in .env with your keys

# 2. Run
docker-compose up -d

# 3. Message your bot on Telegram
```

---

## Adding a new agent

1. Create `agents/my_agent.py` inheriting from `BaseAgent`
2. Define `system_prompt`, `plan()`, and `execute()`
3. Register it in `agents/__init__.py` with its intent keywords
4. Add any new MCP tool access in `mcp/client.py`

That's it. The dispatcher picks it up automatically.

---

## Requirements

- VPS with Docker + Docker Compose
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Anthropic API key
- Google OAuth credentials (for Calendar + Gmail)
- Brave Search API key (free tier works)
- Canva API key (optional, for relationship agent)
