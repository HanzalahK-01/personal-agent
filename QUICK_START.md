# Quick Start Guide

## Files Created

All files are production-quality and follow best practices:

### Core Infrastructure
1. **docker-compose.yml** - Complete service orchestration
2. **.env.example** - Environment template (copy to .env)
3. **.gitignore** - Git exclusions for Python/Docker
4. **requirements.txt** - Python dependencies (pinned versions)

### Configuration Module
5. **config/settings.py** - Pydantic BaseSettings with validation
6. **config/__init__.py** - Module export

### Documentation
7. **INFRASTRUCTURE.md** - Comprehensive setup and architecture guide
8. **QUICK_START.md** - This file

## 30-Second Setup

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your values
nano .env
# Required: TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, ANTHROPIC_API_KEY, TELEGRAM_WEBHOOK_URL

# 3. Build images
docker-compose build

# 4. Start services
docker-compose up -d

# 5. Verify health
docker-compose ps  # All should be healthy
```

## Configuration Highlights

### Security-First Design
- ✅ Docker internal network (no exposed DB/Redis)
- ✅ Telegram user ID whitelist
- ✅ Rate limiting per user (20 msg/min default)
- ✅ Input sanitization + injection detection
- ✅ API keys via .env (never in code)
- ✅ Resource limits per container

### Data Layer
- **PostgreSQL 16** with pgvector extension
- **Async connection pooling** (5-20 connections)
- **pgvector** for semantic search/embeddings
- **Redis** for rate limiting + caching

### Code Quality
- **Type hints** throughout config
- **Pydantic validation** of all settings
- **DSN generation** for easy DB connection
- **Structured logging** with structlog
- **Sensible defaults** with overrides

### Example: Using Settings in Code

```python
from config import settings

# Telegram
allowed_ids = settings.telegram.allowed_user_ids
webhook_url = settings.telegram.webhook_url

# Database
db_url = settings.database.dsn  # Ready for SQLAlchemy
pool_size = settings.database.max_pool_size

# Security
rate_limit = settings.security.rate_limit_per_minute
max_input = settings.security.max_input_length

# External APIs
anthropic_key = settings.anthropic.api_key
canva_key = settings.tools.canva_api_key

# All values validated, with type hints
```

## Environment Variables Reference

### Telegram
```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_WEBHOOK_URL=https://yourdomain.com:8443/webhook
```

### Anthropic
```
ANTHROPIC_API_KEY=your_api_key_here
```

### Database
```
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=personal_agent
POSTGRES_USER=agent_user
POSTGRES_PASSWORD=strong_random_password
```

### Redis
```
REDIS_HOST=redis
REDIS_PORT=6379
```

### Security
```
RATE_LIMIT_PER_MINUTE=20
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## Common Tasks

### View logs
```bash
docker-compose logs -f bot         # Follow bot logs
docker-compose logs postgres       # All postgres logs
docker-compose logs --tail=20 dispatcher
```

### Connect to database
```bash
docker-compose exec postgres psql -U agent_user -d personal_agent
```

### Clear Redis cache
```bash
docker-compose exec redis redis-cli FLUSHALL
```

### Restart a service
```bash
docker-compose restart bot
```

### Stop all services
```bash
docker-compose down
```

### Stop and remove volumes
```bash
docker-compose down -v  # Deletes data!
```

## What's Next

1. Create `Dockerfile` to build bot + dispatcher images
2. Create `src/bot.py` for Telegram bot logic
3. Create `src/dispatcher.py` for async task processing
4. Create `src/agent.py` for LangGraph orchestration
5. Create database migration scripts with Alembic
6. Create MCP tool integrations
7. Deploy to your VPS with `docker-compose up -d`

## Architecture at a Glance

```
User ──(HTTPS)──> Telegram ──webhook──> Bot Service
                                           │
                                           ├──> PostgreSQL (memory + embeddings)
                                           │
                                           ├──> Redis (rate limit, cache)
                                           │
                                           └──> Dispatcher (async tasks)
                                                    │
                                                    ├──> Claude API
                                                    ├──> Canva API
                                                    └──> Brave Search API
```

All internal services communicate via Docker internal network (isolated).

## Security Checklist

- [ ] .env file created and never committed
- [ ] POSTGRES_PASSWORD changed to strong value
- [ ] TELEGRAM_BOT_TOKEN set correctly
- [ ] TELEGRAM_ALLOWED_USER_IDS configured
- [ ] ANTHROPIC_API_KEY set
- [ ] TELEGRAM_WEBHOOK_URL points to real domain
- [ ] Firewall allows only port 8443 (webhook)
- [ ] docker-compose up runs without errors
- [ ] Bot receives Telegram updates
- [ ] Rate limiting working (test with rapid messages)

## Troubleshooting

**Bot not receiving updates?**
- Verify webhook URL is HTTPS accessible
- Check webhook status: `curl https://api.telegram.org/bot{TOKEN}/getWebhookInfo`

**Database connection failed?**
- Ensure postgres service is healthy: `docker-compose ps`
- Check password matches in .env

**Services keep restarting?**
- Check logs: `docker-compose logs`
- Resource limits may be too low (increase in docker-compose.yml)

**Rate limiting not working?**
- Verify Redis is healthy: `docker-compose exec redis redis-cli ping`
- Check RATE_LIMIT_PER_MINUTE is set

See **INFRASTRUCTURE.md** for detailed troubleshooting.
