from __future__ import annotations
"""Plan generation and formatting for the dispatcher."""

import json
import structlog
from typing import Optional

from anthropic import AsyncAnthropic

from config.settings import settings

logger = structlog.get_logger(__name__)

# Initialize Anthropic client
client = AsyncAnthropic(api_key=settings.anthropic.api_key)

# Intents that are simple enough for Haiku when the message is short
_SIMPLE_INTENTS = {"general_chat", "shopping", "routine"}
_SHORT_MESSAGE_THRESHOLD = 50  # characters


def _select_model(intent: str, message: str) -> str:
    """Pick the cheapest model that can handle the request."""
    if intent in _SIMPLE_INTENTS and len(message) <= _SHORT_MESSAGE_THRESHOLD:
        return "claude-haiku-4-5-20251001"
    return "claude-sonnet-4-6"


PLAN_GENERATOR_SYSTEM = """You are a helpful planning assistant. Given a user's request and intent, generate a clear, numbered plan of steps to accomplish the task.

Rules for the plan:
1. Keep each step to 1-2 sentences maximum
2. Use action-oriented language ("Check", "Send", "Schedule", etc.)
3. Maximum 7 steps
4. Each step should be concrete and specific
5. Do not include dangerous actions (system calls, data deletion, account access)

Respond with ONLY a valid JSON object:
{
  "plan": ["Step 1", "Step 2", "Step 3"],
  "estimated_duration": "5 minutes",
  "requires_confirmation": true/false
}"""


async def generate_plan(
    message: str,
    intent: str,
    conversation_history: list[dict] | None = None,
    todoist_context: str = "",
    calendar_context: str = "",
) -> list[str]:
    """
    Generate a step-by-step plan for the user's request.

    Args:
        message: User's original message.
        intent: Classified intent.
        conversation_history: Previous messages for context.
        todoist_context: Live Todoist tasks string.
        calendar_context: Live Google Calendar events string.

    Returns:
        List of plan steps.
    """
    try:
        # Build context
        history_context = ""
        if conversation_history:
            recent_history = conversation_history[-2:]
            for msg in recent_history:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")[:200]  # Truncate
                history_context += f"{role}: {content}\n"

        live_context = "\n\n".join(filter(None, [todoist_context, calendar_context]))

        request_text = (
            f"Context:\n{history_context}\n\n"
            + (f"Live data:\n{live_context}\n\n" if live_context else "")
            + f"Intent: {intent}\n"
            f"Request: {message}"
        )

        model = _select_model(intent, message)
        logger.info("plan_model_selected", model=model, intent=intent, message_len=len(message))

        response = await client.messages.create(
            model=model,
            max_tokens=512,
            system=PLAN_GENERATOR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": request_text,
                }
            ],
        )

        # Strip markdown code fences if present
        response_text = response.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text.strip())

        plan = result.get("plan", [])
        estimated_duration = result.get("estimated_duration", "Unknown")
        requires_confirmation = result.get("requires_confirmation", True)

        # Validate plan
        validated_plan = validate_plan(plan)

        logger.info(
            "plan_generated",
            steps=len(validated_plan),
            duration=estimated_duration,
            requires_confirmation=requires_confirmation,
        )

        return validated_plan

    except json.JSONDecodeError as e:
        logger.error("plan_generation_json_error", error=str(e))
        return ["Unable to generate plan. Please clarify your request."]
    except Exception as e:
        logger.error("plan_generation_error", error=str(e))
        return ["Unable to generate plan. Please try again."]


def validate_plan(plan: list[str]) -> list[str]:
    """
    Validate plan for safety and sanity.

    Args:
        plan: List of plan steps.

    Returns:
        Validated plan list.
    """
    if not plan:
        return []

    if not isinstance(plan, list):
        return []

    # Filter out dangerous patterns
    dangerous_keywords = [
        "rm -rf",
        "delete database",
        "drop table",
        "chmod",
        "sudo",
        "hack",
    ]

    validated = []
    for step in plan:
        if not isinstance(step, str):
            continue

        step_lower = step.lower()
        is_dangerous = any(keyword in step_lower for keyword in dangerous_keywords)

        if is_dangerous:
            logger.warning("dangerous_step_removed", step=step)
            continue

        if len(step) > 200:
            step = step[:197] + "..."

        if step.strip():
            validated.append(step)

    # Cap at 7 steps
    return validated[:7]


def format_plan_message(
    plan: list[str],
    estimated_duration: str = "Unknown",
) -> str:
    """
    Format plan as a clean message for Telegram.

    Args:
        plan: List of plan steps.
        estimated_duration: Estimated time to complete.

    Returns:
        Formatted message string.
    """
    if not plan:
        return "No plan could be generated. Please clarify your request."

    message = "📋 **Proposed Plan**\n\n"

    for i, step in enumerate(plan, 1):
        message += f"{i}. {step}\n"

    message += f"\n⏱️ Estimated duration: {estimated_duration}\n"

    return message


def check_plan_requires_approval(plan: list[str]) -> bool:
    """
    Check if plan requires user approval before execution.

    Args:
        plan: List of plan steps.

    Returns:
        True if approval is needed.
    """
    # All multi-step plans require approval
    if len(plan) > 1:
        return True

    # Single steps that modify state require approval
    approval_keywords = [
        "send",
        "schedule",
        "create",
        "delete",
        "modify",
        "update",
        "confirm",
    ]

    if plan:
        step_lower = plan[0].lower()
        return any(keyword in step_lower for keyword in approval_keywords)

    return False
