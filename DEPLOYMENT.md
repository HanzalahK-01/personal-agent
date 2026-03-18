# Deployment Guide

Everything you need to get `personal-agent` running on a fresh VPS.

---

## Prerequisites

- VPS running Ubuntu 22.04+ (DigitalOcean, Hetzner, Linode, etc.)
- Docker + Docker Compose installed
- The following API keys ready:

| Key | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_USER_WHITELIST` | Your Telegram user ID — send `/start` to [@userinfobot](https://t.me/userinfobot) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `TODOIST_API_TOKEN` | Todoist → Settings → Integrations → API token |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) — free tier is fine |
| Google OAuth credentials | See Google setup below |

---

## 1. Server setup

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

Open port 3000 in your firewall (needed for Google OAuth callback):

```bash
sudo ufw allow 3000/tcp
```

---

## 2. Google OAuth setup (Calendar + Gmail)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create or select a project
3. Go to **APIs & Services → Library** → enable:
   - **Google Calendar API**
   - **Gmail API**
4. Go to **APIs & Services → OAuth consent screen**
   - User type: External
   - Add your Gmail address as a **test user**
5. Go to **Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorized redirect URIs: add `http://YOUR_VPS_IP:3000/oauth2callback`
6. Copy the **Client ID** and **Client Secret** — you'll add them to `.env`

---

## 3. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/personal-agent
cd personal-agent

cp .env.example .env
nano .env
```

Fill in at minimum:

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_USER_WHITELIST=123456789
ANTHROPIC_API_KEY=sk-ant-...
TODOIST_API_TOKEN=your_todoist_token
TAVILY_API_KEY=tvly-...

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://YOUR_VPS_IP:3000/oauth2callback

TIMEZONE=Europe/London
```

---

## 4. Run

```bash
docker compose up -d

# Check it started
docker compose ps

# Watch logs
docker compose logs -f bot
```

---

## 5. Connect Google Calendar / Gmail

Once the bot is running, open Telegram and send:

```
/auth
```

The bot will reply with a Google authorisation URL. Open it in your browser, grant access — Google will redirect to `http://YOUR_VPS_IP:3000/oauth2callback`. The bot catches the callback automatically and saves the token to `./data/google-tokens.json`.

You only need to do this once. Tokens auto-refresh after that.

---

## 6. Keeping it running

```bash
# Update to latest code
git pull
docker compose down
docker compose up -d --build

# Restart the bot
docker compose restart bot

# View logs
docker compose logs -f bot

# Resource usage
docker stats
```

---

## Troubleshooting

**Bot not responding**
```bash
docker compose logs bot --tail=50
# Check TELEGRAM_USER_WHITELIST includes your user ID exactly
```

**Google OAuth redirect_uri_mismatch**
- Make sure the URI in `.env` (`GOOGLE_REDIRECT_URI`) exactly matches what you added in Google Cloud Console
- Make sure port 3000 is open: `sudo ufw allow 3000/tcp`

**Google Calendar 403 error**
- Enable Calendar API and Gmail API in Google Cloud Console → APIs & Services → Library

**Todoist 410 / auth errors**
- Regenerate your API token in Todoist → Settings → Integrations and update `.env`

**MCP tools not working (Gmail/Canva)**
- These route through MCP — run `/auth` in Telegram to reconnect Google services

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Token from BotFather |
| `TELEGRAM_USER_WHITELIST` | ✅ | — | Comma-separated Telegram user IDs |
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key |
| `TODOIST_API_TOKEN` | ☐ | — | Todoist personal API token |
| `TAVILY_API_KEY` | ☐ | — | Tavily web search key |
| `GOOGLE_CLIENT_ID` | ☐ | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ☐ | — | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | ☐ | `http://localhost:3000/oauth2callback` | OAuth callback URI (use VPS IP on server) |
| `DATABASE_URL` | ☐ | — | PostgreSQL URL for memory store (optional) |
| `TIMEZONE` | ☐ | `UTC` | Your local timezone for scheduling |
| `MORNING_DIGEST_TIME` | ☐ | `07:00` | Time for morning digest |
| `RATE_LIMIT_PER_MINUTE` | ☐ | `10` | Messages per minute per user |
| `LOG_LEVEL` | ☐ | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ANTHROPIC_MODEL` | ☐ | `claude-sonnet-4-20250514` | Model override |
