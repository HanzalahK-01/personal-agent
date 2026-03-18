from __future__ import annotations
"""LangGraph state machine for multi-agent dispatch and execution."""

import json
import os
import structlog
from typing import TypedDict, Optional
from datetime import datetime

from anthropic import AsyncAnthropic
from langgraph.graph import StateGraph, END

from config.settings import settings
from dispatcher.router import classify_intent, should_ask_clarification
from dispatcher.planner import generate_plan, validate_plan, check_plan_requires_approval, _select_model
from agents import get_agent_for_intent
from mcp.client import MCPClient

logger = structlog.get_logger(__name__)

# Initialize Anthropic client
client = AsyncAnthropic(api_key=settings.anthropic.api_key)

# Module-level singletons — created once, reused across requests
_mcp_client: Optional[MCPClient] = None
_memory_store = None  # Optional[MemoryStore] — None if DATABASE_URL not set
_memory_store_failed = False  # True after first failed init — stops retrying


def _get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


async def _get_memory_store():
    """Return the MemoryStore singleton, or None if DATABASE_URL is not configured."""
    global _memory_store, _memory_store_failed
    if _memory_store is not None:
        return _memory_store
    if _memory_store_failed:
        return None  # don't retry after first failure

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None

    try:
        from memory.store import MemoryStore
        store = MemoryStore(db_url)
        await store.init()
        _memory_store = store
        logger.info("memory_store_connected")
        return _memory_store
    except Exception as e:
        _memory_store_failed = True
        logger.warning("memory_store_unavailable", error=str(e))
        return None


class DispatcherState(TypedDict):
    """State for the dispatcher graph."""

    message: str
    user_id: int
    intent: str
    intent_confidence: float
    selected_agent: Optional[str]
    plan: list[str]
    approval_status: str  # pending_approval, approved, rejected, completed
    result: str
    memory_context: str
    user_profile: str  # JSON-encoded profile from Supabase
    todoist_context: str
    calendar_context: str
    conversation_history: list[dict]
    error: Optional[str]


# System prompts for different agents

SCHEDULING_AGENT_SYSTEM = """You are a scheduling assistant for a personal AI agent. Help users manage their calendar, schedule events, and manage time. You have access to calendar APIs and can propose scheduling solutions."""

EMAIL_AGENT_SYSTEM = """You are an email assistant. Help users compose, send, and manage emails. Be professional but friendly. Always ask for confirmation before sending."""

ROUTINE_AGENT_SYSTEM = """You are a routine management assistant. Help users create daily tasks, habits, checklists, and reminders. Focus on productivity and consistency."""

SHOPPING_AGENT_SYSTEM = """You are a shopping assistant. Help users create shopping lists, find products, and manage purchases. Be practical and consider budget when suggested."""

RELATIONSHIP_AGENT_SYSTEM = """You are a relationship coordinator. Help users manage social connections, coordinate with others, and send thoughtful messages."""

CONCIERGE_AGENT_SYSTEM = """You are a concierge assistant. Help with general requests including research, recommendations, bookings, and reservations. Be resourceful and thorough."""

GENERAL_CHAT_SYSTEM = """You are a helpful, friendly personal assistant. Answer questions, provide information, and have natural conversations. Be concise and clear."""

AGENT_SYSTEMS = {
    "scheduling": SCHEDULING_AGENT_SYSTEM,
    "email": EMAIL_AGENT_SYSTEM,
    "routine": ROUTINE_AGENT_SYSTEM,
    "shopping": SHOPPING_AGENT_SYSTEM,
    "relationship": RELATIONSHIP_AGENT_SYSTEM,
    "concierge": CONCIERGE_AGENT_SYSTEM,
    "general_chat": GENERAL_CHAT_SYSTEM,
}


async def classify_intent_node(state: DispatcherState) -> DispatcherState:
    """
    Classify user intent from message.

    Node: classify_intent
    """
    logger.info("classify_intent_node_start", user_id=state["user_id"])

    # Load memory context (non-blocking — skipped if DB not configured)
    try:
        memory = await _get_memory_store()
        if memory:
            ctx = await memory.get_context_for_agent(
                user_id=state["user_id"],
                agent_name="dispatcher",
            )
            state["memory_context"] = json.dumps(ctx, default=str)
    except Exception as e:
        logger.warning("memory_context_load_failed", error=str(e))

    # Load user profile from Supabase (non-blocking — skipped if not configured)
    try:
        from integrations.supabase_profile import get_profile
        profile = await get_profile(state["user_id"])
        state["user_profile"] = json.dumps(profile, default=str) if profile else ""
    except Exception as e:
        logger.warning("user_profile_load_failed", error=str(e))

    try:
        intent, confidence = await classify_intent(
            message=state["message"],
            conversation_history=state["conversation_history"],
        )

        state["intent"] = intent
        state["intent_confidence"] = confidence

        # Check if clarification needed
        if await should_ask_clarification(confidence):
            state["approval_status"] = "needs_clarification"
            state[
                "result"
            ] = (
                "I'm not entirely sure what you're asking for. Could you provide more details? "
                "Are you looking to schedule something, send an email, manage tasks, "
                "make a shopping list, coordinate with someone, or something else?"
            )

        logger.info(
            "intent_classified",
            user_id=state["user_id"],
            intent=intent,
            confidence=confidence,
        )

        return state

    except Exception as e:
        logger.error("classify_intent_error", user_id=state["user_id"], error=str(e))
        state["error"] = str(e)
        state["approval_status"] = "error"
        state["result"] = "Unable to process request. Please try again."
        return state


async def route_to_agent_node(state: DispatcherState) -> DispatcherState:
    """
    Route to appropriate agent based on intent.

    Node: route_to_agent
    """
    logger.info(
        "route_to_agent_node_start",
        user_id=state["user_id"],
        intent=state["intent"],
    )

    # Map intent to agent
    intent_to_agent = {
        "scheduling": "scheduling",
        "email": "email",
        "routine": "routine",
        "shopping": "shopping",
        "relationship": "relationship",
        "concierge": "concierge",
        "general_chat": "general_chat",
    }

    state["selected_agent"] = intent_to_agent.get(
        state["intent"], "general_chat"
    )

    logger.info(
        "agent_selected",
        user_id=state["user_id"],
        agent=state["selected_agent"],
    )

    return state


async def generate_plan_node(state: DispatcherState) -> DispatcherState:
    """
    Generate execution plan using selected agent.

    Node: generate_plan
    """
    logger.info(
        "generate_plan_node_start",
        user_id=state["user_id"],
        agent=state["selected_agent"],
    )

    try:
        # Fetch live context so the plan can reference real tasks/events
        todoist_context = ""
        calendar_context = ""
        if state["intent"] in ("routine", "scheduling", "general_chat", "relationship", "concierge"):
            try:
                from integrations.todoist import get_today_tasks
                tasks = await get_today_tasks()
                if tasks:
                    task_lines = []
                    for t in tasks:
                        due = t["due"]["string"] if t.get("due") else "no due date"
                        task_lines.append(f"- [{t['priority']}] {t['content']} (due: {due})")
                    todoist_context = "User's Todoist tasks (today/overdue):\n" + "\n".join(task_lines)
                else:
                    todoist_context = "User has no tasks due today."
            except Exception as e:
                logger.warning("todoist_fetch_failed", error=str(e))

            try:
                from integrations.google_calendar import get_upcoming_events, format_events_for_context
                events = await get_upcoming_events(days=7)
                calendar_context = format_events_for_context(events, days=7)
            except Exception as e:
                logger.warning("google_calendar_fetch_failed", error=str(e))

        state["todoist_context"] = todoist_context
        state["calendar_context"] = calendar_context

        # general_chat goes straight to execution — no plan needed
        if state["intent"] == "general_chat":
            state["plan"] = []
            state["approval_status"] = "approved"
            return state

        # Generate plan
        plan = await generate_plan(
            message=state["message"],
            intent=state["intent"],
            conversation_history=state["conversation_history"],
            todoist_context=todoist_context,
            calendar_context=calendar_context,
        )

        state["plan"] = plan

        # Check if plan requires approval
        if check_plan_requires_approval(plan):
            state["approval_status"] = "pending_approval"
        else:
            state["approval_status"] = "approved"

        logger.info(
            "plan_generated",
            user_id=state["user_id"],
            steps=len(plan),
            requires_approval=state["approval_status"] == "pending_approval",
        )

        return state

    except Exception as e:
        logger.error("generate_plan_error", user_id=state["user_id"], error=str(e))
        state["error"] = str(e)
        state["approval_status"] = "error"
        state["result"] = "Unable to generate plan. Please try again."
        return state


async def await_approval_node(state: DispatcherState) -> DispatcherState:
    """
    Wait for user approval of plan.

    Node: await_approval
    (This node doesn't actually wait - the callback handler updates the state)
    """
    logger.info(
        "await_approval_node_start",
        user_id=state["user_id"],
        plan_steps=len(state["plan"]),
    )

    # Node just marks that we're waiting
    # The callback handler will update state when user approves/rejects/edits

    return state


async def execute_plan_node(state: DispatcherState, progress_callback=None) -> DispatcherState:
    """
    Execute the approved plan.

    Node: execute_plan
    """
    logger.info(
        "execute_plan_node_start",
        user_id=state["user_id"],
        plan_steps=len(state["plan"]),
    )

    try:
        if state["approval_status"] == "rejected":
            state["result"] = "Plan was cancelled. How else can I help?"
            logger.info("plan_rejected", user_id=state["user_id"])
            return state

        # Reuse context fetched during plan generation (no double-fetch)
        todoist_context = state.get("todoist_context", "")
        calendar_context = state.get("calendar_context", "")

        # General chat bypasses the agent system — just use Claude directly
        if state["intent"] == "general_chat":
            model = _select_model(state["intent"], state["message"])
            system = AGENT_SYSTEMS["general_chat"]
            profile_str = state.get("user_profile", "")
            extra_parts = [p for p in [profile_str, todoist_context, calendar_context] if p]
            extra = "\n\n".join(extra_parts)
            if extra:
                system = system + "\n\n" + extra
            response = await client.messages.create(
                model=model,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": state["message"]}],
            )
            state["result"] = response.content[0].text
            state["approval_status"] = "completed"
            return state

        # Instantiate the right agent for this intent
        agent_class = get_agent_for_intent(state["intent"])
        agent = agent_class()

        # Build rich execution context
        context = {
            "message": state["message"],
            "intent": state["intent"],
            "approved_plan": state["plan"],
            "conversation_history": state.get("conversation_history", []),
            "memory": state.get("memory_context", ""),
            "user_profile": state.get("user_profile", ""),
            "todoist_context": todoist_context,
            "calendar_context": calendar_context,
        }

        # Let the agent generate its own technical plan steps
        plan_steps = await agent.plan(state["message"], context)

        # Execute via MCP client
        mcp_client = _get_mcp_client()
        exec_result = await agent.execute(plan_steps, context, mcp_client, progress_callback=progress_callback)

        # Reflect into a user-friendly reply
        result_text = await agent.reflect(exec_result)
        state["result"] = result_text
        state["approval_status"] = "completed"

        # Persist conversation to memory (fire-and-forget)
        try:
            memory = await _get_memory_store()
            if memory:
                agent_name = state.get("selected_agent", "general")
                await memory.save_conversation(
                    user_id=state["user_id"],
                    agent=agent_name,
                    message=state["message"],
                    role="user",
                )
                await memory.save_conversation(
                    user_id=state["user_id"],
                    agent=agent_name,
                    message=result_text,
                    role="assistant",
                )
        except Exception as e:
            logger.warning("memory_save_failed", error=str(e))

        logger.info(
            "plan_executed",
            user_id=state["user_id"],
            agent=agent_class.__name__,
            steps_completed=len(exec_result.steps_completed),
            steps_failed=len(exec_result.steps_failed),
            result_length=len(result_text),
        )

        return state

    except Exception as e:
        logger.error("execute_plan_error", user_id=state["user_id"], error=str(e))
        state["error"] = str(e)
        state["approval_status"] = "error"
        state[
            "result"
        ] = "Unable to execute plan. Please try again or contact support."
        return state


async def format_response_node(state: DispatcherState) -> DispatcherState:
    """
    Format final response for user.

    Node: format_response
    """
    logger.info(
        "format_response_node_start",
        user_id=state["user_id"],
        approval_status=state["approval_status"],
    )

    # If no result set yet, create one
    if not state.get("result"):
        if state["approval_status"] == "pending_approval":
            state["result"] = "Plan ready for approval."
        elif state["approval_status"] == "error":
            state["result"] = "An error occurred. Please try again."
        else:
            state["result"] = "Done!"

    logger.info("response_formatted", user_id=state["user_id"])
    return state


def _should_generate_plan(state: DispatcherState) -> str:
    """Routing logic: should we generate a plan?"""
    if state.get("error") or state["approval_status"] == "error":
        return "format_response"

    if state["approval_status"] == "needs_clarification":
        return "format_response"

    return "generate_plan"


def _should_execute(state: DispatcherState) -> str:
    """Routing logic: should we execute the approved plan?"""
    if state["approval_status"] == "approved":
        return "execute_plan"
    elif state["approval_status"] == "pending_approval":
        return "await_approval"
    else:
        return "format_response"


def build_graph() -> StateGraph:
    """
    Build the LangGraph state machine.

    Returns:
        Compiled StateGraph.
    """
    graph = StateGraph(DispatcherState)

    # Add nodes
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("route_to_agent", route_to_agent_node)
    graph.add_node("generate_plan", generate_plan_node)
    graph.add_node("await_approval", await_approval_node)
    graph.add_node("execute_plan", execute_plan_node)
    graph.add_node("format_response", format_response_node)

    # Define edges
    graph.add_edge("classify_intent", "route_to_agent")
    graph.add_edge("route_to_agent", "generate_plan")

    # Conditional edges
    graph.add_conditional_edges(
        "generate_plan",
        _should_execute,
        {
            "execute_plan": "execute_plan",
            "await_approval": "await_approval",
            "format_response": "format_response",
        },
    )

    graph.add_edge("await_approval", "format_response")
    graph.add_edge("execute_plan", "format_response")
    graph.add_edge("format_response", END)

    # Set entry point
    graph.set_entry_point("classify_intent")

    return graph


# Build and compile graph
_graph = build_graph()
dispatcher_graph = _graph.compile()


async def dispatch_message(
    user_id: int,
    message_text: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Dispatch a message through the graph.

    Args:
        user_id: Telegram user ID.
        message_text: The message text.
        conversation_history: Previous conversation turns.

    Returns:
        Final state dict with result.
    """
    logger.info(
        "dispatch_message_start",
        user_id=user_id,
        message_length=len(message_text),
    )

    try:
        # Initialize state
        initial_state: DispatcherState = {
            "message": message_text,
            "user_id": user_id,
            "intent": "",
            "intent_confidence": 0.0,
            "selected_agent": None,
            "plan": [],
            "approval_status": "pending",
            "result": "",
            "memory_context": "",
            "user_profile": "",
            "todoist_context": "",
            "calendar_context": "",
            "conversation_history": conversation_history or [],
            "error": None,
        }

        # Run through graph
        final_state = await dispatcher_graph.ainvoke(initial_state)

        logger.info(
            "dispatch_message_complete",
            user_id=user_id,
            intent=final_state.get("intent"),
            status=final_state.get("approval_status"),
        )

        return final_state

    except Exception as e:
        logger.error("dispatch_message_error", user_id=user_id, error=str(e))
        return {
            "message": message_text,
            "user_id": user_id,
            "approval_status": "error",
            "result": "An error occurred processing your request.",
            "error": str(e),
        }
