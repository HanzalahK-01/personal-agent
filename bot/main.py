from __future__ import annotations
"""Main Telegram bot application with webhook support."""

import asyncio
import structlog
from contextlib import asynccontextmanager

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import TelegramError

from config.settings import settings
from bot.handlers import (
    handle_start,
    handle_message,
    handle_callback,
    handle_auth,
    handle_authcode,
    handle_plan,
    handle_add,
    handle_done,
    handle_remove,
    handle_rejig,
    handle_status,
    handle_profile,
)
from bot.security import UserAuth, RateLimiter, InputSanitizer, security_check

logger = structlog.get_logger(__name__)


class TelegramBotApp:
    """Telegram bot application with security and dispatcher integration."""

    def __init__(self):
        """Initialize bot application."""
        self.application: Application | None = None
        self.user_auth: UserAuth | None = None
        self.rate_limiter: RateLimiter | None = None
        self.sanitizer: InputSanitizer | None = None

    async def initialize(self) -> None:
        """
        Initialize bot application and components.

        Validates configuration, initializes security components,
        registers handlers.
        """
        try:
            # Validate config
            self._validate_config()

            # Initialize security components
            logger.info("initializing_security_components")
            self.user_auth = UserAuth(whitelist=settings.telegram.user_whitelist)
            self.rate_limiter = RateLimiter(
                redis_url=settings.redis.url
            )
            self.sanitizer = InputSanitizer(
                max_length=settings.security.max_input_length
            )

            # Connect rate limiter to Redis
            await self.rate_limiter.connect()

            # Create Telegram Application
            logger.info("creating_telegram_application")
            self.application = Application.builder().token(
                settings.telegram.bot_token
            ).build()

            # Register handlers
            self._register_handlers()

            # Set up middleware for security checks
            self._setup_middleware()

            self.application.post_init = self._post_init
            self.application.post_stop = self._post_stop

            logger.info("bot_initialization_complete")

        except Exception as e:
            logger.error("bot_initialization_failed", error=str(e))
            raise

    def _validate_config(self) -> None:
        """Validate required configuration."""
        required_fields = [
            ("telegram.bot_token", settings.telegram.bot_token),
            ("telegram.user_whitelist", settings.telegram.user_whitelist),
            ("redis.url", settings.redis.url),
            ("anthropic.api_key", settings.anthropic.api_key),
        ]

        for field_name, field_value in required_fields:
            if not field_value:
                raise ValueError(f"Missing required config: {field_name}")

        if len(settings.telegram.user_whitelist) == 0:
            raise ValueError("User whitelist is empty")

        logger.info(
            "config_validation_passed",
            whitelist_size=len(settings.telegram.user_whitelist),
        )

    def _register_handlers(self) -> None:
        """Register Telegram message and command handlers."""
        if not self.application:
            raise RuntimeError("Application not initialized")

        # Command handlers
        self.application.add_handler(CommandHandler("start", handle_start))
        self.application.add_handler(CommandHandler("auth", handle_auth))
        self.application.add_handler(CommandHandler("authcode", handle_authcode))
        self.application.add_handler(CommandHandler("plan", handle_plan))
        self.application.add_handler(CommandHandler("add", handle_add))
        self.application.add_handler(CommandHandler("done", handle_done))
        self.application.add_handler(CommandHandler("remove", handle_remove))
        self.application.add_handler(CommandHandler("rejig", handle_rejig))
        self.application.add_handler(CommandHandler("status", handle_status))
        self.application.add_handler(CommandHandler("profile", handle_profile))

        # Message handler (must come before callback to avoid conflicts)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        # Callback handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(handle_callback))

        logger.info("handlers_registered")

    def _setup_middleware(self) -> None:
        """Set up request middleware for security checks."""
        if not self.application:
            raise RuntimeError("Application not initialized")

        async def security_middleware(update: Update, context) -> None:
            """Inject security components into context and check auth."""
            if update.effective_user:
                user_id = update.effective_user.id

                # Inject security components into context
                if not hasattr(context, "user_data"):
                    context.user_data = {}

                context.user_data["user_id"] = user_id
                context.user_data["user_auth"] = self.user_auth
                context.user_data["rate_limiter"] = self.rate_limiter
                context.user_data["sanitizer"] = self.sanitizer

                # For message handlers, run security checks
                if update.message and update.message.text:
                    is_safe, reason = await security_check(
                        user_id=user_id,
                        message_text=update.message.text,
                        user_auth=self.user_auth,
                        rate_limiter=self.rate_limiter,
                        sanitizer=self.sanitizer,
                    )

                    if not is_safe:
                        logger.warning(
                            "message_blocked_by_security",
                            user_id=user_id,
                            reason=reason,
                        )
                        # Send generic error (don't expose reason)
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text="Your message could not be processed.",
                            )
                        except TelegramError as e:
                            logger.error(
                                "send_blocked_message_error",
                                error=str(e),
                            )
                        return  # Don't process this update

        # Attach middleware
        self.application.add_error_handler(self._error_handler)
        logger.info("middleware_configured")

    async def _post_init(self, context) -> None:
        """Post-initialization setup."""
        logger.info("bot_post_init_starting")
        try:
            logger.info("bot_ready", bot_username=context.bot.username)
        except Exception as e:
            logger.error("post_init_error", error=str(e))

    async def _post_stop(self, context) -> None:
        """Post-stop cleanup."""
        logger.info("bot_post_stop_starting")
        try:
            if self.rate_limiter:
                await self.rate_limiter.disconnect()
            logger.info("bot_stopped")
        except Exception as e:
            logger.error("post_stop_error", error=str(e))

    async def _error_handler(self, update: object, context) -> None:
        """Handle errors that occur during update processing."""
        try:
            raise context.error
        except TelegramError as e:
            logger.error("telegram_error", error=str(e), update=str(update))
        except Exception as e:
            logger.error("unexpected_error", error=str(e), update=str(update))

    async def run_webhook(self) -> None:
        """
        Run bot in webhook mode (production).

        Requires webhook_domain and webhook_url to be configured.
        """
        if not self.application:
            raise RuntimeError("Application not initialized")

        try:
            webhook_domain = settings.webhook.domain
            webhook_url = settings.webhook.url
            webhook_port = settings.webhook.port

            if not webhook_domain or not webhook_url:
                raise ValueError(
                    "webhook_domain and webhook_url required for webhook mode"
                )

            logger.info(
                "starting_webhook_mode",
                url=webhook_url,
                port=webhook_port,
            )

            async with self.application:
                await self.application.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=["message", "callback_query"],
                )
                logger.info("webhook_set", url=webhook_url)

                await self.application.start()
                logger.info("bot_started")

                # Run indefinitely
                await asyncio.Event().wait()

        except Exception as e:
            logger.error("webhook_error", error=str(e))
            raise

    async def run_polling(self) -> None:
        """
        Run bot in polling mode (development).

        Continuously polls Telegram for updates.
        """
        if not self.application:
            raise RuntimeError("Application not initialized")

        try:
            logger.info("starting_polling_mode")

            async with self.application:
                await self.application.start()
                logger.info("bot_started")

                # Poll for updates
                await self.application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    timeout=30,
                )

                # Run indefinitely
                await asyncio.Event().wait()

        except KeyboardInterrupt:
            logger.info("polling_interrupted_by_user")
        except Exception as e:
            logger.error("polling_error", error=str(e))
            raise
        finally:
            logger.info("bot_shutting_down")
            if self.application:
                await self.application.stop()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("shutdown_requested")
        if self.application:
            await self.application.stop()
        if self.rate_limiter:
            await self.rate_limiter.disconnect()
        logger.info("shutdown_complete")


@asynccontextmanager
async def bot_context():
    """Context manager for bot lifecycle."""
    bot = TelegramBotApp()
    await bot.initialize()
    try:
        yield bot
    finally:
        await bot.shutdown()


async def main() -> None:
    """Main entry point."""
    try:
        async with bot_context() as bot:
            # Determine mode from config
            if settings.telegram.use_webhook:
                await bot.run_webhook()
            else:
                await bot.run_polling()
    except Exception as e:
        logger.error("main_error", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
