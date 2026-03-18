from __future__ import annotations
#!/usr/bin/env python3
"""
Configuration Validation Script

Validates that all required environment variables are set and valid.
Run before deploying to catch configuration errors early.

Usage:
    python validate_config.py
"""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import settings


def validate_telegram() -> bool:
    """Validate Telegram configuration."""
    print("Validating Telegram config...")

    try:
        assert settings.telegram.bot_token, "TELEGRAM_BOT_TOKEN not set"
        assert settings.telegram.bot_token.count(":") == 1, \
            "TELEGRAM_BOT_TOKEN format invalid (should be ID:TOKEN)"
        print(f"  ✓ Bot token: {settings.telegram.bot_token[:10]}...")

        assert settings.telegram.allowed_user_ids, \
            "TELEGRAM_ALLOWED_USER_IDS not set (empty list)"
        assert len(settings.telegram.allowed_user_ids) > 0, \
            "TELEGRAM_ALLOWED_USER_IDS must contain at least one user ID"
        print(f"  ✓ Allowed user IDs: {len(settings.telegram.allowed_user_ids)} users")

        assert settings.telegram.webhook_url, "TELEGRAM_WEBHOOK_URL not set"
        assert settings.telegram.webhook_url.startswith("https://"), \
            "TELEGRAM_WEBHOOK_URL must be HTTPS"
        print(f"  ✓ Webhook URL: {settings.telegram.webhook_url}")

        assert settings.telegram.webhook_port in [80, 443, 88, 8443], \
            f"Webhook port {settings.telegram.webhook_port} not allowed by Telegram"
        print(f"  ✓ Webhook port: {settings.telegram.webhook_port}")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_anthropic() -> bool:
    """Validate Anthropic configuration."""
    print("Validating Anthropic config...")

    try:
        assert settings.anthropic.api_key, "ANTHROPIC_API_KEY not set"
        assert settings.anthropic.api_key.startswith("sk-"), \
            "ANTHROPIC_API_KEY should start with 'sk-'"
        print(f"  ✓ API key: {settings.anthropic.api_key[:20]}...")

        assert settings.anthropic.max_tokens > 0, \
            "max_tokens must be > 0"
        print(f"  ✓ Max tokens: {settings.anthropic.max_tokens}")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_database() -> bool:
    """Validate database configuration."""
    print("Validating Database config...")

    try:
        assert settings.database.host, "POSTGRES_HOST not set"
        print(f"  ✓ Host: {settings.database.host}")

        assert settings.database.port > 0, "POSTGRES_PORT must be > 0"
        print(f"  ✓ Port: {settings.database.port}")

        assert settings.database.database, "POSTGRES_DB not set"
        print(f"  ✓ Database: {settings.database.database}")

        assert settings.database.user, "POSTGRES_USER not set"
        print(f"  ✓ User: {settings.database.user}")

        # Password check
        if settings.database.password == "change_me_in_production":
            print("  ⚠ WARNING: Using default POSTGRES_PASSWORD")
            if settings.environment == "production":
                print("  ✗ ERROR: Must change password in production!")
                return False
        else:
            print(f"  ✓ Password: [configured]")

        # Validate DSN can be generated
        dsn = settings.database.dsn
        assert "postgresql+asyncpg://" in dsn, "Invalid DSN format"
        print(f"  ✓ DSN generated successfully")

        assert settings.database.max_pool_size > 0, \
            "max_pool_size must be > 0"
        assert settings.database.min_pool_size > 0, \
            "min_pool_size must be > 0"
        assert settings.database.min_pool_size <= settings.database.max_pool_size, \
            "min_pool_size cannot be > max_pool_size"
        print(f"  ✓ Connection pool: {settings.database.min_pool_size}-"
              f"{settings.database.max_pool_size}")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_redis() -> bool:
    """Validate Redis configuration."""
    print("Validating Redis config...")

    try:
        assert settings.redis.host, "REDIS_HOST not set"
        print(f"  ✓ Host: {settings.redis.host}")

        assert settings.redis.port > 0, "REDIS_PORT must be > 0"
        print(f"  ✓ Port: {settings.redis.port}")

        # Validate URL can be generated
        url = settings.redis.url
        assert url.startswith("redis://"), "Invalid Redis URL format"
        print(f"  ✓ URL generated successfully")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_security() -> bool:
    """Validate security configuration."""
    print("Validating Security config...")

    try:
        assert settings.security.rate_limit_per_minute > 0, \
            "RATE_LIMIT_PER_MINUTE must be > 0"
        print(f"  ✓ Rate limit: {settings.security.rate_limit_per_minute} msg/min")

        assert settings.security.max_input_length > 0, \
            "max_input_length must be > 0"
        print(f"  ✓ Max input length: {settings.security.max_input_length} chars")

        assert settings.security.request_timeout_seconds > 0, \
            "request_timeout_seconds must be > 0"
        print(f"  ✓ Request timeout: {settings.security.request_timeout_seconds}s")

        if settings.security.enable_injection_detection:
            print(f"  ✓ Injection detection: enabled")
        else:
            print(f"  ⚠ WARNING: Injection detection disabled")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_general() -> bool:
    """Validate general configuration."""
    print("Validating General config...")

    try:
        assert settings.environment in ["production", "staging", "development"], \
            f"Invalid ENVIRONMENT: {settings.environment}"
        print(f"  ✓ Environment: {settings.environment}")

        assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], \
            f"Invalid LOG_LEVEL: {settings.log_level}"
        print(f"  ✓ Log level: {settings.log_level}")

        return True
    except AssertionError as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_optional_tools() -> bool:
    """Validate optional tool integrations."""
    print("Validating Optional Tools...")

    checks_passed = True

    if settings.canva.client_id and settings.canva.client_secret:
        print(f"  ✓ Canva: configured")
    else:
        print(f"  ⚠ Canva: not configured (optional)")

    if settings.tavily.api_key:
        print(f"  ✓ Tavily Search: configured")
    else:
        print(f"  ⚠ Tavily Search: not configured (optional)")

    return checks_passed


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("Configuration Validation")
    print("=" * 60)
    print()

    checks = [
        ("Telegram", validate_telegram),
        ("Anthropic", validate_anthropic),
        ("Database", validate_database),
        ("Redis", validate_redis),
        ("Security", validate_security),
        ("General", validate_general),
        ("Optional Tools", validate_optional_tools),
    ]

    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))
        print()

    # Summary
    print("=" * 60)
    passed = sum(1 for _, result in results if result)
    total = len(results)

    if passed == total:
        print(f"✓ All {total} configuration checks passed!")
        print("=" * 60)
        return 0
    else:
        print(f"✗ {total - passed} of {total} checks failed!")
        print("=" * 60)
        print("\nFailed checks:")
        for name, result in results:
            if not result:
                print(f"  - {name}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
