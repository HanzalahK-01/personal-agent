from __future__ import annotations
"""Google OAuth2 authentication helper.

Flow:
  1. Call get_auth_url() → send URL to user
  2. User visits URL, grants access, copies the code
  3. Call exchange_code(code) → saves tokens to data/google-tokens.json
  4. Subsequent calls to get_credentials() auto-refresh as needed.
"""

import json
import os
from pathlib import Path
from typing import Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config.settings import settings

logger = structlog.get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

_TOKEN_PATH = Path("data/google-tokens.json")
_CREDS_PATH = Path("data/google-credentials.json")  # written for MCP servers


def _client_config() -> dict:
    """Build the OAuth2 client config dict from settings."""
    return {
        "installed": {
            "client_id": settings.google.client_id,
            "client_secret": settings.google.client_secret,
            "redirect_uris": [settings.google.redirect_uri, "urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _build_flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google.redirect_uri,
    )


def get_auth_url() -> str:
    """Return the Google OAuth2 authorization URL."""
    flow = _build_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    logger.info("google_auth_url_generated")
    return auth_url


def exchange_code(code: str) -> Credentials:
    """
    Exchange an authorization code for tokens and persist them.

    Args:
        code: The authorization code from Google.

    Returns:
        google.oauth2.credentials.Credentials
    """
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    _save_credentials(creds)
    logger.info("google_tokens_exchanged_and_saved")
    return creds


async def run_local_auth_server() -> Optional[str]:
    """
    Start a one-shot local HTTP server on port 3000 to catch the OAuth callback.

    Waits up to 5 minutes for the user to complete the flow.
    Returns the authorization code, or None on timeout/error.
    """
    import asyncio
    from aiohttp import web

    code_future: asyncio.Future = asyncio.get_event_loop().create_future()

    async def _callback(request: web.Request) -> web.Response:
        code = request.rel_url.query.get("code")
        error = request.rel_url.query.get("error")
        if code and not code_future.done():
            code_future.set_result(code)
            return web.Response(
                text="<html><body><h2>Connected! You can close this tab and return to Telegram.</h2></body></html>",
                content_type="text/html",
            )
        if error and not code_future.done():
            code_future.set_result(None)
        return web.Response(text="Auth error. Please try again.", content_type="text/html")

    app = web.Application()
    app.router.add_get("/oauth2callback", _callback)
    runner = web.AppRunner(app)
    await runner.setup()
    # Bind to 0.0.0.0 so the callback is reachable on a VPS
    site = web.TCPSite(runner, "0.0.0.0", 3000)
    await site.start()
    logger.info("google_auth_local_server_started", port=3000)

    try:
        code = await asyncio.wait_for(code_future, timeout=300)
    except asyncio.TimeoutError:
        logger.warning("google_auth_local_server_timeout")
        code = None
    finally:
        await runner.cleanup()

    return code


def get_credentials() -> Optional[Credentials]:
    """
    Load saved credentials, refreshing if expired.

    Returns:
        Credentials if authenticated, None otherwise.
    """
    if not _TOKEN_PATH.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)
    except Exception as e:
        logger.error("google_credentials_load_failed", error=str(e))
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            logger.info("google_credentials_refreshed")
        except Exception as e:
            logger.error("google_credentials_refresh_failed", error=str(e))
            return None

    return creds if creds.valid else None


def is_authenticated() -> bool:
    """Return True if valid Google credentials exist."""
    return get_credentials() is not None


def _save_credentials(creds: Credentials) -> None:
    """Persist credentials to disk and write the MCP-compatible credentials file."""
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Save user token file (used by get_credentials())
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    _TOKEN_PATH.write_text(json.dumps(token_data, indent=2))

    # Write a combined credentials file that MCP servers can consume
    mcp_creds = {
        **_client_config(),
        "token": token_data,
    }
    _CREDS_PATH.write_text(json.dumps(mcp_creds, indent=2))

    logger.info("google_credentials_saved", token_path=str(_TOKEN_PATH))
