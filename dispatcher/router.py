from __future__ import annotations
"""Intent classification router using Claude."""

import json
import structlog
from typing import Optional

from anthropic import AsyncAnthropic

from config.settings import settings

logger = structlog.get_logger(__name__)

# Initialize Anthropic client
client = AsyncAnthropic(api_key=settings.anthropic.api_key)


INTENT_CLASSIFIER_SYSTEM = """You are an intent classifier for a personal AI assistant. Classify the user's message into one of these categories:

1. **scheduling** - Calendar events, meeting scheduling, time management
2. **email** - Composing, sending, or managing emails
3. **routine** - Daily tasks, habits, checklists, reminders
4. **shopping** - Creating or managing shopping lists, finding products
5. **relationship** - Social coordination, messages to contacts, relationship management
6. **concierge** - General requests (research, booking, reservations, info)
7. **general_chat** - Casual conversation, questions, chat

Respond with a JSON object containing:
{
  "intent": "<one of the categories above>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>"
}

Only respond with valid JSON."""


async def classify_intent(
    message: str,
    conversation_history: list[dict] | None = None,
) -> tuple[str, float]:
    """
    Classify user message intent using Claude.

    Args:
        message: User's message to classify.
        conversation_history: Previous messages for context.

    Returns:
        Tuple of (intent, confidence). intent is one of the 7 categories.
    """
    try:
        # Build context from conversation history
        history_context = ""
        if conversation_history:
            recent_history = conversation_history[-4:]  # Last 2 exchanges
            for msg in recent_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_context += f"{role.upper()}: {content}\n"

        full_message = (
            f"Previous context:\n{history_context}\n\nNew message: {message}"
            if history_context
            else message
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=INTENT_CLASSIFIER_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": full_message,
                }
            ],
        )

        # Parse response — strip markdown code fences if present
        response_text = response.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text.strip())

        intent = result.get("intent", "general_chat")
        confidence = float(result.get("confidence", 0.5))
        reasoning = result.get("reasoning", "")

        # Validate intent
        valid_intents = [
            "scheduling",
            "email",
            "routine",
            "shopping",
            "relationship",
            "concierge",
            "general_chat",
        ]
        if intent not in valid_intents:
            intent = "general_chat"
            confidence = 0.5

        logger.info(
            "intent_classified",
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
        )

        return intent, confidence

    except json.JSONDecodeError as e:
        logger.error("intent_classification_json_error", error=str(e))
        return "general_chat", 0.5
    except Exception as e:
        logger.error("intent_classification_error", error=str(e))
        return "general_chat", 0.5


async def should_ask_clarification(confidence: float, threshold: float = 0.7) -> bool:
    """
    Determine if intent confidence is too low and needs clarification.

    Args:
        confidence: Intent classification confidence score.
        threshold: Minimum confidence required (default 0.7).

    Returns:
        True if clarification is needed.
    """
    return confidence < threshold
