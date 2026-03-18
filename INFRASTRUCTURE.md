# Personal AI Agent - Infrastructure Files

This directory contains production-quality infrastructure files for a multi-agent personal assistant system running on a VPS.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network (Internal)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │     Bot      │  │ Dispatcher   │  │  PostgreSQL  │      │
│  │ (Telegram)   │  │ (Async Tasks)│  │  + pgvector  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                   │             │
│         └─────────────────┼───────────────────┘             │
│                           │                                 │
│                    ┌──────────────┐                         │
│                    │    Redis     │                         │
│                    │(Rate Limit)  │                         │
│                    └──────────────┘                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
           ▲
           │ HTTPS Webhook (8443)
           │ Telegram only
           ▼
      [Internet]
```

## Files Overview

### 1. **docker-compose.yml**
Complete Docker Compose configuration for the entire system.

**Services:**
- **postgres** (pgvector/pgvector:pg16-latest)
  - PostgreSQL with pgvector extension for semantic search
  - Persistent volume: `postgres_data`
  - Health checks enabled
  - Resource limits: 1 CPU, 512MB RAM

- **redis** (redis:7-alpine)
  - Redis for rate limiting and caching
  - LRU eviction policy (256MB max)
  - Persistent volume: `redis_data`
  - Health checks enabled
  - Resource limits: 0.5 CPU, 256MB RAM

- **bot** (built from ./Dockerfile)
  - Telegram bot service with webhook
  - Only external port exposed: 8443 (HTTPS webhook)
  - Depends on postgres and redis health
  - Resource limits: 2 CPU, 1GB RAM

- **dispatcher** (built from ./Dockerfile)
  - Background task processing
  - Communicates with other services via internal network
  - Shares same Dockerfile as bot
  - Resource limits: 2 CPU, 1GB RAM

**Network:**
- `internal` bridge network: services can reach each other by name
- Only bot has external port access (8443)
- All services isolated from host network except webhook port

**Security Features:**
- Internal network isolation
- No exposed database or Redis ports
- Resource limits prevent runaway processes
- Restart policy: `unless-stopped`

### 2. **.env.example**
Template for environment variables. **Must be copied to `.env` before running.**

**Required Variables:**
- `TELEGRAM_BOT_TOKEN`: From @BotFather
- `TELEGRAM_ALLOWED_USER_IDS`: Comma-separated list of authorized user IDs
- `TELEGRAM_WEBHOOK_URL`: HTTPS webhook URL
- `ANTHROPIC_API_KEY`: From Anthropic console
- `POSTGRES_PASSWORD`: Strong password for DB
- `CANVA_API_KEY`: For design generation (optional)
- `BRAVE_SEARCH_API_KEY`: For web search (optional)

**Production Checklist:**
- [ ] Change `POSTGRES_PASSWORD` to strong, random value
- [ ] Set `ENVIRONMENT=production`
- [ ] Set `LOG_LEVEL=WARNING` (reduce logs)
- [ ] Configure `TELEGRAM_WEBHOOK_URL` with actual domain
- [ ] Configure `TELEGRAM_ALLOWED_USER_IDS` with actual user IDs
- [ ] Set rate limit appropriate for your usage

### 3. **.gitignore**
Standard Python + Docker + IDE gitignore patterns.

**Key Ignored Files:**
- `.env` (never commit secrets)
- `__pycache__/`, `*.pyc`
- `venv/`, `ENV/`
- `.vscode/`, `.idea/`
- `*.log`, `logs/`
- Docker volumes and backups

### 4. **requirements.txt**
Production dependencies with pinned versions.

**Key Packages:**
- **anthropic**: Claude API client
- **langgraph**: Agent orchestration framework
- **python-telegram-bot[webhooks]**: Telegram integration
- **asyncpg, pgvector, sqlalchemy**: Database
- **redis[asyncio]**: Caching and rate limiting
- **pydantic, pydantic-settings**: Configuration management
- **structlog**: Structured logging

**Note:** Development tools (pytest, black, mypy) are commented out. Create `requirements-dev.txt` if needed.

### 5. **config/settings.py** + **config/__init__.py**
Pydantic-based configuration management.

**Structure:**
```python
Settings
├── TelegramConfig (bot_token, allowed_user_ids, webhook_url, webhook_port)
├── AnthropicConfig (api_key, model, max_tokens, timeout)
├── DatabaseConfig (host, port, database, user, password, pool settings, DSN)
├── RedisConfig (host, port, password, database, connection settings)
├── SecurityConfig (rate_limit_per_minute, injection_detection, max_input_length)
└── ToolsConfig (canva_api_key, brave_search_api_key)
```

**Usage:**
```python
from config import settings

# Access settings
bot_token = settings.telegram.bot_token
db_dsn = settings.database.dsn
rate_limit = settings.security.rate_limit_per_minute

# All settings are validated
# Type checking and defaults built-in
```

**Features:**
- Automatic .env loading
- Environment variable override support
- Type validation with Pydantic
- Sensible defaults where appropriate
- DSN generation for database connections
- Sensitive values hidden in repr() output

## Getting Started

### 1. Prepare .env file
```bash
cp .env.example .env
# Edit .env with actual values
```

### 2. Create required directories
```bash
mkdir -p scripts logs data
```

### 3. Initialize PostgreSQL (optional init script)
Create `scripts/init-postgres.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4. Build and start services
```bash
docker-compose build
docker-compose up -d
```

### 5. Verify services
```bash
docker-compose ps  # All services should be healthy
docker-compose logs bot  # Check bot logs
docker-compose logs -f postgres  # Follow postgres logs
```

## Database Migrations

Using SQLAlchemy + Alembic (recommended setup):

```bash
# Generate migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head

# In docker-compose, migrations can run as init container
```

## Monitoring

### Docker logs
```bash
# Follow bot logs
docker-compose logs -f bot

# Follow all services
docker-compose logs -f

# Show recent postgres logs
docker-compose logs --tail=50 postgres
```

### Database health
```bash
docker-compose exec postgres psql -U agent_user -d personal_agent -c "SELECT 1;"
```

### Redis health
```bash
docker-compose exec redis redis-cli ping
```

## Security Best Practices

1. **Secrets Management**
   - Never commit `.env` to git
   - Use strong, random `POSTGRES_PASSWORD`
   - Rotate `TELEGRAM_BOT_TOKEN` if compromised
   - Use `.env.local` for local overrides

2. **Network Security**
   - Only port 8443 exposed (Telegram webhook)
   - Internal network isolates services
   - Configure firewall to allow only known Telegram IPs
   - Use HTTPS for webhook (required by Telegram)

3. **Database Security**
   - Change default PostgreSQL password
   - Use connection pooling (enabled by default)
   - Set command timeout to prevent hanging queries
   - Use pgvector indexes for performance

4. **Rate Limiting**
   - `RATE_LIMIT_PER_MINUTE=20` prevents abuse
   - Implement user-level and global limits
   - Log suspicious activity

5. **Input Validation**
   - Prompt injection detection enabled by default
   - Max input length: 10000 characters
   - Sanitize all user inputs

## Performance Tuning

### Database
- Adjust `max_pool_size` based on concurrency needs
- pgvector indexes for semantic search queries
- Connection pooling reduces overhead

### Redis
- LRU eviction: old keys removed when memory full
- Adjust max memory (256MB by default)
- Use for caching frequently accessed data

### Bot
- Webhook mode is more efficient than polling
- Async I/O prevents blocking
- Rate limiting prevents resource exhaustion

## Troubleshooting

### Bot not receiving Telegram updates
- Verify `TELEGRAM_WEBHOOK_URL` is accessible HTTPS
- Check Telegram webhook is set: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Ensure port 8443 is open and forwarded

### Database connection errors
- Check postgres service is healthy: `docker-compose ps postgres`
- Verify `POSTGRES_PASSWORD` is correct
- Check connection DSN: `docker-compose exec bot python -c "from config import settings; print(settings.database.dsn)"`

### Rate limiting too strict/loose
- Adjust `RATE_LIMIT_PER_MINUTE` in .env
- Monitor Redis usage: `docker-compose exec redis redis-cli INFO memory`

### Out of memory
- Reduce `max_pool_size` for database
- Reduce Redis `maxmemory` in docker-compose
- Check for memory leaks: `docker stats`

## Deployment Checklist

- [ ] Copy .env.example to .env
- [ ] Update all environment variables with production values
- [ ] Set ENVIRONMENT=production
- [ ] Configure HTTPS webhook with real domain
- [ ] Set up log aggregation (stdout → Docker logs)
- [ ] Configure firewall for port 8443
- [ ] Backup strategy for PostgreSQL
- [ ] Monitor service health
- [ ] Set up alerts for service failures
- [ ] Document custom environment variables

## Additional Resources

- [docker-compose docs](https://docs.docker.com/compose/)
- [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [PostgreSQL + pgvector](https://github.com/pgvector/pgvector)
- [Redis async client](https://redis-py.readthedocs.io/)
- [Anthropic API docs](https://docs.anthropic.com/)
