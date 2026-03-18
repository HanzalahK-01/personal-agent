from __future__ import annotations
"""
Base agent class for the personal AI agent system.

Provides core planning, execution, and reflection capabilities.
All specialized agents inherit from BaseAgent.
"""

import asyncio
import json
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum

from anthropic import AsyncAnthropic

logger = structlog.get_logger()


class ActionType(str, Enum):
    """Types of actions an agent can plan."""
    RETRIEVE = "retrieve"
    ANALYZE = "analyze"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SEARCH = "search"
    SUGGEST = "suggest"
    SCHEDULE = "schedule"


@dataclass
class PlanStep:
    """A single step in an agent's plan."""
    step_number: int
    action: str
    tool: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ExecutionResult:
    """Result of executing a plan."""
    success: bool
    steps_completed: List[PlanStep]
    steps_failed: List[tuple[PlanStep, str]]
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "steps_completed": [s.to_dict() for s in self.steps_completed],
            "steps_failed": [(s.to_dict(), error) for s, error in self.steps_failed],
            "summary": self.summary,
            "data": self.data,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the personal AI system.

    Provides:
    - Planning via Claude with structured reasoning
    - Step-by-step execution with error handling and retries
    - Reflection on results for learning and improvement
    - Structured logging with agent context
    """

    def __init__(self, name: str, description: str, capabilities: List[str]):
        """
        Initialize a base agent.

        Args:
            name: Agent name for identification
            description: Human-readable description of agent purpose
            capabilities: List of what this agent can do
        """
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.client = AsyncAnthropic()

        # Execution context
        self.max_retries_per_step = 2
        self._logger = structlog.get_logger().bind(agent=name)

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        Return the system prompt for this agent.
        Must be implemented by each specialized agent.
        """
        pass

    async def plan(
        self,
        message: str,
        context: Dict[str, Any],
        memory: Optional[Dict[str, Any]] = None,
    ) -> List[PlanStep]:
        """
        Use Claude to generate a step-by-step plan for the given message.

        Args:
            message: The user's request or task
            context: Dict with current state (calendar, emails, lists, etc.)
            memory: Optional previous interactions and learned patterns

        Returns:
            List of PlanStep objects representing the execution plan
        """
        memory = memory or {}

        # Select model — Haiku for simple intents, Sonnet for complex ones
        intent = context.get("intent", "")
        _simple = {"routine", "shopping", "general_chat"}
        model = "claude-haiku-4-5-20251001" if intent in _simple else "claude-sonnet-4-6"

        # Build compact context — skip heavy fields to save tokens
        compact_context = {
            k: v for k, v in context.items()
            if k not in ("conversation_history", "memory", "approved_plan", "user_profile")
        }
        context_str = json.dumps(compact_context, indent=2, default=str)[:2000]

        # Inject user profile as a concise header if available
        user_profile_hint = ""
        raw_profile = context.get("user_profile", "")
        if raw_profile:
            try:
                import json as _json
                profile = _json.loads(raw_profile)
                from integrations.supabase_profile import format_profile_for_context
                user_profile_hint = "\n" + format_profile_for_context(profile)
            except Exception:
                pass

        # Inject dispatcher's approved plan as a hint so we don't start from scratch
        approved_plan = context.get("approved_plan", [])
        approved_hint = ""
        if approved_plan:
            approved_hint = "\nAPPROVED HIGH-LEVEL PLAN (follow this):\n" + "\n".join(
                f"- {s}" for s in approved_plan
            )

        planning_prompt = f"""
You are an AI agent tasked with planning how to help the user.
{user_profile_hint}
CAPABILITIES: You can use these tools and methods:
{chr(10).join(f"- {cap}" for cap in self.capabilities)}

USER REQUEST: {message}

CURRENT CONTEXT:
{context_str}
{approved_hint}

Generate a detailed plan as a JSON array of steps. Each step should have:
- step_number (int): Sequential step number
- action (str): What to do (e.g., "fetch_emails", "check_calendar", "search_web")
- tool (str): The specific tool/method to use (e.g., "gmail.search_messages", "gcal.list_events")
- parameters (object): Parameters for the tool call
- description (str): Human-readable description of this step

RULES:
1. Break the task into 3-7 concrete steps
2. Each step should be actionable and specific
3. Use ONLY the exact tool names and parameter names listed below — do not invent new ones
4. For tool names, use format: "service.method"
5. Return ONLY a valid JSON array, no other text
6. Use the `description` field on tasks to capture supporting details, notes, or bullet-point lists (e.g. packing list items, reminder notes, addresses). Format multi-item descriptions as newline-separated bullet points: "• item one\n• item two". Keep task `content` as a short title.
7. ALWAYS include `duration` (in minutes) on every todoist.add_task call.
 Duration is the difference between the task's start and end time. If the user gives both a start and end time, compute duration = end − start in minutes. If only one time or no time is given, estimate a realistic duration based on the task — e.g. a quick errand 15 min, grocery run 45 min, packing 60–90 min, a meeting 30–60 min, a gym session 60 min, admin/email 20 min. Never omit it.

AVAILABLE TOOLS — use these exact names and parameters:

todoist.get_tasks
  params: (none)

todoist.get_today_tasks
  params: (none)

todoist.add_task
  params: content (str, required), description (str, optional — extra detail, notes, bullet points for the task body), priority ("high"|"medium"|"low"), due_date ("YYYY-MM-DD"), due_time ("HH:MM" — the start time), due_string (natural language, e.g. "tomorrow at 9am"), duration (int, minutes — end time minus start time; estimate if not specified), duration_unit ("minute")

todoist.update_task
  params: task_id (str) OR task_match (str, name to search), content (str), description (str, optional — replaces the task description/notes), priority ("high"|"medium"|"low"), due_date ("YYYY-MM-DD"), due_time ("HH:MM")

todoist.complete_task
  params: task_id (str)

todoist.delete_task
  params: task_id (str)

todoist.find_task
  params: name (str)

gcal.list_events
  params: days (int, default 7)

gcal.get_today_events
  params: (none)

gcal.create_event
  params: summary (str, required), start_dt (ISO 8601 datetime, e.g. "2026-03-20T14:00:00+00:00"), end_dt (ISO 8601 datetime), description (str, optional), location (str, optional)

tavily.search
  params: query (str), max_results (int, default 5)

tavily.search_news
  params: query (str), max_results (int, default 5)

gmail.search_messages
  params: query (str, Gmail search syntax e.g. "from:boss is:unread"), max_results (int, default 10)

gmail.read_message
  params: message_id (str)

gmail.read_thread
  params: thread_id (str)

gmail.create_draft
  params: to (str), subject (str), body (str)

supabase.get_profile
  params: (none) — returns the user's stored profile (name, timezone, notes, preferences)

supabase.update_profile
  params: one or more of: name (str), timezone (str), notes (str), preferences (dict)
  — use this to save things the user tells you about themselves (preferences, habits, facts)
"""

        self._logger.info(
            "planning",
            request=message,
            capabilities_count=len(self.capabilities),
        )

        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=600,
                system=self.system_prompt,
                messages=[{"role": "user", "content": planning_prompt}],
            )

            plan_text = response.content[0].text

            # Parse JSON plan — handle markdown fences and stray text
            import re as _re
            text = plan_text.strip()
            # Strip ```json ... ``` or ``` ... ``` fences
            text = _re.sub(r'^```(?:json)?\s*', '', text)
            text = _re.sub(r'\s*```$', '', text.strip())
            try:
                plan_data = json.loads(text)
            except json.JSONDecodeError:
                # Try to extract a JSON array from anywhere in the response
                json_match = _re.search(r'\[.*?\]', text, _re.DOTALL)
                if json_match:
                    plan_data = json.loads(json_match.group())
                else:
                    raise ValueError("Could not parse plan as JSON")

            # Validate and convert to PlanStep objects
            steps = []
            for step_data in plan_data:
                step = PlanStep(
                    step_number=step_data.get("step_number", len(steps) + 1),
                    action=step_data.get("action", ""),
                    tool=step_data.get("tool"),
                    parameters=step_data.get("parameters", {}),
                    description=step_data.get("description", ""),
                )
                steps.append(step)

            self._logger.info("plan_generated", steps_count=len(steps))
            return steps

        except Exception as e:
            self._logger.error("planning_failed", error=str(e))
            raise

    async def execute(
        self,
        plan: List[PlanStep],
        context: Dict[str, Any],
        mcp_client: Any,
        progress_callback: Any = None,
    ) -> ExecutionResult:
        """
        Execute an approved plan step by step with error handling and retries.

        Args:
            plan: List of PlanStep objects to execute
            context: Current context and state
            mcp_client: MCP client for tool invocation

        Returns:
            ExecutionResult with success status and detailed outcomes
        """
        completed_steps: List[PlanStep] = []
        failed_steps: List[tuple[PlanStep, str]] = []
        execution_data: Dict[str, Any] = {}

        self._logger.info("execution_started", plan_length=len(plan))

        for step in plan:
            self._logger.info(
                "executing_step",
                step_number=step.step_number,
                action=step.action,
                tool=step.tool,
            )

            retry_count = 0
            step_succeeded = False
            step_error = ""

            while retry_count <= self.max_retries_per_step and not step_succeeded:
                try:
                    # Execute the step via MCP client
                    if step.tool:
                        result = await self._execute_tool_call(
                            step.tool,
                            step.parameters,
                            mcp_client,
                            context=context,
                        )

                        # Store result for later steps
                        execution_data[f"step_{step.step_number}"] = result
                        step_succeeded = True

                        self._logger.info(
                            "step_completed",
                            step_number=step.step_number,
                            tool=step.tool,
                        )
                        if progress_callback:
                            await progress_callback(step, True, None)
                    else:
                        # Analysis step with no tool call
                        self._logger.info(
                            "analysis_step",
                            step_number=step.step_number,
                        )
                        step_succeeded = True
                        execution_data[f"step_{step.step_number}"] = {
                            "analysis": step.description
                        }

                except Exception as e:
                    step_error = str(e)
                    retry_count += 1

                    self._logger.warning(
                        "step_execution_failed",
                        step_number=step.step_number,
                        retry_count=retry_count,
                        error=step_error,
                    )

                    if retry_count <= self.max_retries_per_step:
                        # Exponential backoff before retry
                        await asyncio.sleep(2 ** retry_count)

            if step_succeeded:
                completed_steps.append(step)
            else:
                failed_steps.append((step, step_error))
                if progress_callback:
                    await progress_callback(step, False, step_error)

        success = len(failed_steps) == 0

        self._logger.info(
            "execution_finished",
            success=success,
            completed=len(completed_steps),
            failed=len(failed_steps),
        )

        return ExecutionResult(
            success=success,
            steps_completed=completed_steps,
            steps_failed=failed_steps,
            summary=self._build_summary(completed_steps, failed_steps),
            data=execution_data,
        )

    async def reflect(self, result: ExecutionResult) -> str:
        """
        Reflect on an execution result and generate a summary for the user.

        Args:
            result: The ExecutionResult from executing a plan

        Returns:
            Human-readable summary of what was accomplished
        """
        reflection_prompt = f"""
You are an AI agent reflecting on the results of your actions.

EXECUTION RESULT:
Success: {result.success}
Steps Completed: {len(result.steps_completed)}
Steps Failed: {len(result.steps_failed)}

COMPLETED STEPS:
{chr(10).join(f"- {s.description}" for s in result.steps_completed)}

{f"FAILED STEPS:" + chr(10) + chr(10).join(f"- {s.description}: {error}" for s, error in result.steps_failed) if result.steps_failed else ""}

DATA RETRIEVED:
{json.dumps(result.data, indent=2, default=str)}

Generate a brief, friendly summary (2-3 sentences) of what was accomplished and any next steps if needed.
"""

        self._logger.info("reflecting_on_result")

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=250,
                system=self.system_prompt,
                messages=[{"role": "user", "content": reflection_prompt}],
            )

            summary = response.content[0].text
            self._logger.info("reflection_complete")
            return summary

        except Exception as e:
            self._logger.error("reflection_failed", error=str(e))
            return result.summary

    def _build_summary(
        self,
        completed_steps: List[PlanStep],
        failed_steps: List[tuple[PlanStep, str]],
    ) -> str:
        """Build a summary of execution results."""
        if not failed_steps:
            return f"Successfully completed all {len(completed_steps)} steps."
        return (
            f"Completed {len(completed_steps)} steps, "
            f"but {len(failed_steps)} step(s) failed. "
            f"Please try again or adjust your request."
        )

    async def _execute_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        mcp_client: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool call, routing to direct integrations or MCP as appropriate.
        """
        if "." not in tool_name:
            self._logger.warning("tool_name_no_service", tool=tool_name)
            return {"skipped": True, "reason": f"tool '{tool_name}' has no service prefix"}

        service, method = tool_name.split(".", 1)

        self._logger.debug("tool_call_start", tool=tool_name, parameters=parameters)

        try:
            if service == "todoist":
                result = await _call_todoist(method, parameters)
            elif service == "gcal":
                result = await _call_gcal(method, parameters)
            elif service == "tavily":
                result = await _call_tavily(method, parameters)
            elif service == "supabase":
                user_id = (context or {}).get("user_id")
                result = await _call_supabase(method, parameters, user_id)
            elif service == "assistant":
                result = await _call_assistant(method, parameters)
            else:
                # Fall through to MCP for gmail, canva, etc.
                result = await mcp_client.call_tool(
                    server_name=service,
                    tool_name=method,
                    arguments=parameters,
                )

            self._logger.debug("tool_call_success", tool=tool_name)
            return result

        except Exception as e:
            self._logger.error("tool_call_failed", tool=tool_name, error=str(e))
            raise


# ---------------------------------------------------------------------------
# Direct integration routers — called instead of MCP for known services
# ---------------------------------------------------------------------------

async def _call_todoist(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from integrations.todoist import (
        get_tasks, get_today_tasks, add_task,
        complete_task, delete_task, update_task, find_task_by_name,
    )
    if method == "get_tasks":
        return {"tasks": await get_tasks()}
    if method == "get_today_tasks":
        return {"tasks": await get_today_tasks()}
    # create_task / add_task — accept either name
    if method in ("add_task", "create_task"):
        content = params.get("content") or params.get("title") or params.get("name", "")
        if not content:
            return {"error": "add_task requires a content/title/name parameter"}
        # Build due_string from separate date + time fields if needed
        due_string = params.get("due_string") or params.get("due")
        if not due_string:
            due_date = params.get("due_date", "")
            due_time = params.get("due_time", "")
            if due_date and due_time:
                due_string = f"{due_date} {due_time}"
            elif due_date:
                due_string = due_date
        task = await add_task(
            content=content,
            priority=params.get("priority", "medium"),
            due_string=due_string,
            labels=params.get("labels"),
            description=params.get("description"),
            duration=int(params.get("duration", 30)),
            duration_unit=params.get("duration_unit", "minute"),
        )
        return {"task": task}

    if method == "complete_task":
        task_id = params.get("task_id")
        if not task_id:
            match = params.get("task_match") or params.get("name") or params.get("content", "")
            found = await find_task_by_name(match)
            if not found:
                return {"error": f"Task not found: {match}"}
            task_id = found["id"]
        ok = await complete_task(task_id)
        return {"success": ok}

    if method == "delete_task":
        task_id = params.get("task_id")
        if not task_id:
            match = params.get("task_match") or params.get("name") or params.get("content", "")
            found = await find_task_by_name(match)
            if not found:
                return {"error": f"Task not found: {match}"}
            task_id = found["id"]
        ok = await delete_task(task_id)
        return {"success": ok}

    if method == "update_task":
        # Agent sometimes passes a list of tasks under "tasks" key — handle batch
        task_list = params.get("tasks")
        if task_list and isinstance(task_list, list):
            results = []
            for item in task_list:
                results.append(await _do_update_task(item))
            return {"results": results}
        return await _do_update_task(params)

    if method == "find_task":
        found = await find_task_by_name(params.get("name", ""))
        return {"task": found}

    raise ValueError(f"Unknown todoist method: {method}")


async def _do_update_task(params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve task ID and apply updates for a single task."""
    from integrations.todoist import update_task, find_task_by_name

    task_id = params.get("task_id")

    # Resolve by name/match if no real ID provided
    if not task_id or not str(task_id).replace("-", "").isalnum() or len(str(task_id)) < 10:
        match = params.get("task_match") or params.get("name") or params.get("content", "")
        found = await find_task_by_name(match)
        if not found:
            return {"error": f"Task not found: {match}"}
        task_id = found["id"]

    # Normalise field names — agent uses new_name/title/name for content
    updates: Dict[str, Any] = {}
    content = params.get("new_name") or params.get("new_content") or params.get("title")
    if content:
        updates["content"] = content

    if params.get("priority"):
        updates["priority"] = params["priority"]

    # Build due_string from separate fields if needed
    due_string = params.get("due_string") or params.get("due")
    if not due_string:
        due_date = params.get("due_date", "")
        due_time = params.get("due_time", "")
        if due_date and due_time:
            due_string = f"{due_date} {due_time}"
        elif due_date:
            due_string = due_date
    if due_string:
        updates["due_string"] = due_string

    if params.get("description") is not None:
        updates["description"] = params["description"]

    if not updates:
        return {"skipped": True, "reason": "no updates to apply"}

    task = await update_task(task_id, **updates)
    return {"task": task}


async def _call_gcal(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from integrations.google_calendar import get_upcoming_events, get_today_events, create_event
    if method in ("list_events", "get_events"):
        days = params.get("days", 7)
        events = await get_upcoming_events(days=days)
        return {"events": events}
    if method == "get_today_events":
        events = await get_today_events()
        return {"events": events}
    if method == "create_event":
        result = await create_event(
            summary=params.get("summary", params.get("title", "")),
            start_dt=params.get("start_dt", params.get("start", "")),
            end_dt=params.get("end_dt", params.get("end", "")),
            description=params.get("description", ""),
            location=params.get("location", ""),
        )
        return result
    return {"note": f"gcal.{method} not yet supported natively", "params": params}


async def _call_tavily(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from integrations.tavily import search, search_news
    if method == "search":
        results = await search(params.get("query", ""), max_results=params.get("max_results", 5))
        return {"results": results}
    if method == "search_news":
        results = await search_news(params.get("query", ""), max_results=params.get("max_results", 5))
        return {"results": results}
    raise ValueError(f"Unknown tavily method: {method}")


async def _call_supabase(method: str, params: Dict[str, Any], user_id: Optional[int]) -> Dict[str, Any]:
    from integrations.supabase_profile import get_profile, upsert_profile
    if not user_id:
        return {"error": "user_id not available for supabase call"}
    if method == "get_profile":
        profile = await get_profile(user_id)
        return {"profile": profile}
    if method == "update_profile":
        # Accept any kwargs as profile fields to update
        update_data = {k: v for k, v in params.items()}
        profile = await upsert_profile(user_id, update_data)
        return {"profile": profile}
    raise ValueError(f"Unknown supabase method: {method}")


async def _call_assistant(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fake 'assistant.*' tools the agent sometimes generates — just pass data through."""
    return {"result": params, "method": method}
