from __future__ import annotations
"""Security module for Telegram bot with user auth, rate limiting, and input validation."""

import asyncio
import re
import structlog
from datetime import datetime, timedelta
from typing import Optional, Tuple
from functools import wraps

import redis.asyncio as aioredis
from config.settings import settings

logger = structlog.get_logger(__name__)


class UserAuth:
    """Validates Telegram user ID against whitelist."""

    def __init__(self, whitelist: list[int] | None = None):
        """
        Initialize UserAuth with optional whitelist.

        Args:
            whitelist: List of allowed Telegram user IDs. If None, uses settings.
        """
        self.whitelist = whitelist or settings.telegram.user_whitelist
        logger.info("user_auth_initialized", whitelist_count=len(self.whitelist))

    async def is_authorized(self, user_id: int) -> bool:
        """
        Check if user ID is in whitelist.

        Args:
            user_id: Telegram user ID to validate.

        Returns:
            True if user is authorized, False otherwise.
        """
        is_auth = user_id in self.whitelist
        log_level = "info" if is_auth else "warning"
        getattr(logger, log_level)(
            "user_auth_check",
            user_id=user_id,
            authorized=is_auth,
        )
        return is_auth


class RateLimiter:
    """Rate limiting using Redis with sliding window algorithm."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Initialize RateLimiter.

        Args:
            redis_url: Redis connection URL.
        """
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.rate_limit_per_minute = settings.security.rate_limit_per_minute

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = await aioredis.from_url(self.redis_url)
            logger.info("rate_limiter_connected", redis_url=self.redis_url)
        except Exception as e:
            logger.error("rate_limiter_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("rate_limiter_disconnected")

    async def check_rate_limit(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if user has exceeded rate limit.

        Uses sliding window: count messages in last 60 seconds.

        Args:
            user_id: Telegram user ID.

        Returns:
            Tuple of (is_allowed, reason). reason is None if allowed.
        """
        if not self.redis:
            logger.warning("rate_limiter_no_redis_connection")
            return True, None

        try:
            key = f"rate_limit:{user_id}"
            now = datetime.utcnow().timestamp()
            window_start = now - 60  # 60-second window

            # Remove old entries
            await self.redis.zremrangebyscore(key, 0, window_start)

            # Count messages in window
            count = await self.redis.zcard(key)

            if count >= self.rate_limit_per_minute:
                reason = (
                    f"Rate limit exceeded: {self.rate_limit_per_minute} "
                    f"messages per minute"
                )
                logger.warning(
                    "rate_limit_exceeded",
                    user_id=user_id,
                    count=count,
                    limit=self.rate_limit_per_minute,
                )
                return False, reason

            # Add current timestamp
            await self.redis.zadd(key, {str(now): now})
            await self.redis.expire(key, 60)

            logger.debug(
                "rate_limit_check_passed",
                user_id=user_id,
                current_count=count + 1,
            )
            return True, None

        except Exception as e:
            logger.error("rate_limit_check_error", user_id=user_id, error=str(e))
            # Fail open: allow on error but log it
            return True, None


class InputSanitizer:
    """Validates and sanitizes user input for prompt injection and abuse."""

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        r"ignore\s+(?:previous|prior|all)\s+(?:instructions|prompts|messages)",
        r"(?:system|admin|override)\s*:",
        r"forget\s+(?:everything|previous|instructions)",
        r"new\s+(?:instructions|task|goal|system)",
        r"(?:forget|ignore)\s+.{0,20}?(?:instructions|role|rules)",
        r"you\s+(?:are|are now)\s+(?:a|an)\s+(?:different|new)",
        r"(?:pretend|imagine|assume)\s+(?:you\s+)?(?:are|\'re)\s+",
        r"(?:act|behave|respond)\s+as\s+(?:a|an|if\s+you\s+were)",
        r"(?:as\s+)?(?:an\s+)?(?:jailbreak|exploit|bypass)",
    ]

    # Compile patterns for efficiency
    COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in INJECTION_PATTERNS]

    def __init__(self, max_length: int = 2000):
        """
        Initialize InputSanitizer.

        Args:
            max_length: Maximum allowed input length in characters.
        """
        self.max_length = max_length

    def sanitize(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check input for injection attempts and abuse.

        Args:
            text: User input to validate.

        Returns:
            Tuple of (is_safe, reason). reason is None if safe.
        """
        if not isinstance(text, str):
            return False, "Input must be string"

        # Check length
        if len(text) > self.max_length:
            return (
                False,
                f"Input exceeds maximum length of {self.max_length} characters",
            )

        # Check for injection patterns
        text_lower = text.lower()
        for pattern in self.COMPILED_PATTERNS:
            if pattern.search(text_lower):
                reason = "Input contains suspicious patterns"
                logger.warning(
                    "injection_pattern_detected",
                    pattern=pattern.pattern,
                )
                return False, reason

        # Check for excessive special characters (more than 30% special chars)
        special_char_count = sum(
            1 for c in text if not c.isalnum() and not c.isspace()
        )
        special_ratio = special_char_count / len(text) if text else 0
        if special_ratio > 0.3:
            logger.warning(
                "suspicious_special_chars",
                ratio=special_ratio,
            )
            return False, "Input contains excessive special characters"

        # Check for null bytes
        if "\x00" in text:
            return False, "Input contains null bytes"

        logger.debug("input_sanitization_passed", length=len(text))
        return True, None


async def security_check(
    user_id: int,
    message_text: str,
    user_auth: UserAuth,
    rate_limiter: RateLimiter,
    sanitizer: InputSanitizer,
) -> Tuple[bool, Optional[str]]:
    """
    Run complete security checks in sequence.

    Returns early on first failure.

    Args:
        user_id: Telegram user ID.
        message_text: Message text to validate.
        user_auth: UserAuth instance.
        rate_limiter: RateLimiter instance.
        sanitizer: InputSanitizer instance.

    Returns:
        Tuple of (is_safe, reason). reason is None if all checks pass.
    """
    # Check 1: User authorization
    if not await user_auth.is_authorized(user_id):
        return False, "Unauthorized user"

    # Check 2: Rate limiting
    allowed, reason = await rate_limiter.check_rate_limit(user_id)
    if not allowed:
        return False, reason

    # Check 3: Input sanitization
    is_safe, reason = sanitizer.sanitize(message_text)
    if not is_safe:
        return False, reason

    logger.info("security_check_passed", user_id=user_id)
    return True, None


def secured(func):
    """
    Decorator that wraps handler functions with security checks.

    Assumes function has signature:
        async def handler(update, context, ...) or similar
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract user_id from context (second argument in Telegram handlers)
        try:
            if len(args) > 1:
                context = args[1]
            else:
                context = kwargs.get("context")

            user_id = context.user_data.get("user_id")
            if not user_id:
                logger.error("secured_decorator_missing_user_id")
                return

            # Get instances from context
            user_auth = context.user_data.get("user_auth")
            rate_limiter = context.user_data.get("rate_limiter")
            sanitizer = context.user_data.get("sanitizer")

            if not all([user_auth, rate_limiter, sanitizer]):
                logger.error("secured_decorator_missing_security_instances")
                return

            # Run security checks
            is_safe, reason = await security_check(
                user_id,
                kwargs.get("message_text", ""),
                user_auth,
                rate_limiter,
                sanitizer,
            )

            if not is_safe:
                # Log and return early without exposing details
                logger.warning("security_check_failed", user_id=user_id, reason=reason)
                return

            # Call original function
            return await func(*args, **kwargs)

        except Exception as e:
            logger.error("secured_decorator_error", error=str(e))
            return

    return wrapper
