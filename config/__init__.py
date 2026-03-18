"""
Configuration module for Personal AI Agent.

Exports:
    settings: Global Settings instance loaded from environment variables
"""

from config.settings import Settings

# Global settings instance loaded from .env and environment variables
settings = Settings()

__all__ = ["settings", "Settings"]
