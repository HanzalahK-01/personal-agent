from __future__ import annotations
"""Configuration settings for the personal AI agent system."""

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""

    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    user_whitelist: list[int] = field(default_factory=lambda: _parse_whitelist())
    use_webhook: bool = field(default_factory=lambda: os.getenv("USE_WEBHOOK", "false").lower() == "true")


@dataclass
class WebhookConfig:
    """Webhook configuration for production."""

    domain: str = field(default_factory=lambda: os.getenv("WEBHOOK_DOMAIN", ""))
    url: str = field(default_factory=lambda: os.getenv("WEBHOOK_URL", ""))
    port: int = field(default_factory=lambda: int(os.getenv("WEBHOOK_PORT", "8443")))


@dataclass
class RedisConfig:
    """Redis configuration for rate limiting."""

    url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))


@dataclass
class AnthropicConfig:
    """Anthropic API configuration."""

    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))


@dataclass
class TavilyConfig:
    """Tavily search API configuration."""

    api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))


@dataclass
class CanvaConfig:
    """Canva OAuth configuration."""

    client_id: str = field(default_factory=lambda: os.getenv("CANVA_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("CANVA_CLIENT_SECRET", ""))


@dataclass
class TodoistConfig:
    """Todoist API configuration."""

    api_token: str = field(default_factory=lambda: os.getenv("TODOIST_API_TOKEN", ""))


@dataclass
class GoogleConfig:
    """Google OAuth configuration (Calendar / Gmail)."""

    client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", ""))
    redirect_uri: str = field(
        default_factory=lambda: os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/oauth2callback")
    )


@dataclass
class PlannerConfig:
    """Daily planner configuration."""

    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Europe/London"))
    morning_digest_time: str = field(
        default_factory=lambda: os.getenv("MORNING_DIGEST_TIME", "07:00")
    )
    evening_review_time: str = field(
        default_factory=lambda: os.getenv("EVENING_REVIEW_TIME", "18:00")
    )


@dataclass
class SupabaseConfig:
    """Supabase project configuration (used for user profile REST API)."""

    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))


@dataclass
class SecurityConfig:
    """Security configuration."""

    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    max_input_length: int = field(
        default_factory=lambda: int(os.getenv("MAX_INPUT_LENGTH", "2000"))
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )


@dataclass
class Settings:
    """Root configuration object."""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    todoist: TodoistConfig = field(default_factory=TodoistConfig)
    tavily: TavilyConfig = field(default_factory=TavilyConfig)
    canva: CanvaConfig = field(default_factory=CanvaConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    def validate(self) -> None:
        """Validate all required settings."""
        if not self.telegram.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if not self.anthropic.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        if not self.telegram.user_whitelist:
            raise ValueError("TELEGRAM_USER_WHITELIST not set or empty")


def _parse_whitelist() -> list[int]:
    """
    Parse user whitelist from environment variable.

    Expects comma-separated user IDs: "123456,789012,345678"
    """
    whitelist_str = os.getenv("TELEGRAM_USER_WHITELIST", "")
    if not whitelist_str:
        return []

    try:
        return [int(uid.strip()) for uid in whitelist_str.split(",") if uid.strip()]
    except ValueError as e:
        raise ValueError(f"Invalid TELEGRAM_USER_WHITELIST format: {e}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.validate()
    return settings


# Singleton instance
settings = get_settings()
