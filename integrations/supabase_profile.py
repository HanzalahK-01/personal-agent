from __future__ import annotations
"""Supabase user profile store via PostgREST (REST API, IPv4-safe, no asyncpg)."""

import httpx
import structlog
from typing import Optional

from config.settings import settings

logger = structlog.get_logger(__name__)

_TABLE = "user_profiles"


def _is_configured() -> bool:
    return bool(settings.supabase.url and settings.supabase.anon_key)


def _base_url() -> str:
    return f"{settings.supabase.url.rstrip('/')}/rest/v1"


def _headers(prefer: str = "return=representation") -> dict:
    key = settings.supabase.anon_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def get_profile(user_id: int) -> Optional[dict]:
    """
    Fetch the user profile row from Supabase.

    Returns the profile dict or None if not found / Supabase not configured.
    """
    if not _is_configured():
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_base_url()}/{_TABLE}",
                headers=_headers(),
                params={"user_id": f"eq.{user_id}", "select": "*"},
                timeout=10,
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                logger.info("supabase_profile_fetched", user_id=user_id)
                return rows[0]
            return None
    except Exception as e:
        logger.warning("supabase_get_profile_failed", user_id=user_id, error=str(e))
        return None


async def upsert_profile(user_id: int, data: dict) -> dict:
    """
    Create or update the user profile. ``data`` is merged into the existing row.

    Example fields: name, timezone, notes, preferences (dict).
    Returns the saved profile dict.
    """
    if not _is_configured():
        return {}

    payload = {"user_id": str(user_id), **data}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_base_url()}/{_TABLE}",
                headers=_headers(prefer="resolution=merge-duplicates,return=representation"),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            rows = resp.json()
            logger.info("supabase_profile_upserted", user_id=user_id, keys=list(data.keys()))
            return rows[0] if rows else payload
    except Exception as e:
        logger.error("supabase_upsert_profile_failed", user_id=user_id, error=str(e))
        return {}


def format_profile_for_context(profile: Optional[dict]) -> str:
    """
    Convert a profile dict into a compact string for injection into agent system prompts.
    Returns empty string if no profile.
    """
    if not profile:
        return ""

    lines = ["USER PROFILE:"]
    if profile.get("name"):
        lines.append(f"  Name: {profile['name']}")
    if profile.get("timezone"):
        lines.append(f"  Timezone: {profile['timezone']}")
    if profile.get("notes"):
        lines.append(f"  Notes: {profile['notes']}")
    if profile.get("preferences"):
        prefs = profile["preferences"]
        if isinstance(prefs, dict):
            for k, v in prefs.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"  Preferences: {prefs}")
    return "\n".join(lines)


# SQL to create the table — run this once in your Supabase SQL editor:
#
# CREATE TABLE IF NOT EXISTS user_profiles (
#   user_id TEXT PRIMARY KEY,
#   name TEXT,
#   timezone TEXT DEFAULT 'UTC',
#   notes TEXT,
#   preferences JSONB DEFAULT '{}',
#   updated_at TIMESTAMPTZ DEFAULT NOW()
# );
#
# -- Enable Row Level Security (optional but recommended)
# ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
