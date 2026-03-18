from __future__ import annotations
"""Tavily search API integration (async via httpx)."""

import httpx
import structlog
from typing import Optional

from config.settings import settings

logger = structlog.get_logger(__name__)

TAVILY_BASE_URL = "https://api.tavily.com"


async def search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = True,
    topic: str = "general",
) -> dict:
    """
    Search the web via Tavily.

    Args:
        query: Search query string.
        max_results: Number of results to return (max 10).
        search_depth: "basic" (faster) or "advanced" (more thorough).
        include_answer: Whether to include an AI-generated answer summary.
        topic: "general" or "news".

    Returns:
        Dict with keys: answer (str), results (list of {title, url, content, score})
    """
    payload = {
        "api_key": settings.tavily.api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "topic": topic,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TAVILY_BASE_URL}/search",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()

    data = resp.json()
    logger.info("tavily_search_complete", query=query, results=len(data.get("results", [])))
    return {
        "answer": data.get("answer", ""),
        "results": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in data.get("results", [])
        ],
    }


async def search_news(query: str, max_results: int = 5) -> dict:
    """Search recent news via Tavily."""
    return await search(query, max_results=max_results, topic="news")
