from __future__ import annotations
"""Telegram message handlers for the personal AI agent."""

import structlog
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config.settings import settings
from dispatcher.graph import dispatch_message
from integrations import todoist as todoist_api
from integrations import google_auth
from integrations.daily_planner import (
    generate_daily_plan,
    write_plan_to_todoist,
    rejig_day,
    add_task_to_plan,
    mark_task_complete,
    format_plan_for_telegram,
)

logger = structlog.get_logger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command with welcome message.

    Args:
        update: Telegram update object.
        context: Telegram context object.
    """
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"

    welcome_message = (
        f"👋 Welcome, {username}!\n\n"
        "I'm your personal AI assistant powered by Claude. I can help with:\n\n"
        "📅 **Scheduling** - Manage your calendar\n"
        "📧 **Email** - Compose and send messages\n"
        "✅ **Routines** - Daily task management\n"
        "🛒 **Shopping** - Build and track lists\n"
        "💬 **Relationships** - Social coordination\n"
        "🎯 **Concierge** - General requests\n"
        "💭 **Chat** - Just talk to me\n\n"
        "**Quick commands:**\n"
        "/plan — See today's time-boxed schedule\n"
        "/add <task> — Add a task to Todoist\n"
        "/done <task> — Mark a task complete\n"
        "/remove <task> — Delete a task\n"
        "/rejig — Reorganise the rest of your day\n"
        "/status — Check today's progress\n"
        "/profile — View or update your profile (name, timezone, notes)"
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=welcome_message,
            parse_mode="Markdown",
        )
        logger.info("start_command_sent", user_id=user_id)
    except Exception as e:
        logger.error("start_command_error", user_id=user_id, error=str(e))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming text messages.

    Sends to dispatcher, awaits plan approval, then executes.

    Args:
        update: Telegram update object with message.
        context: Telegram context object.
    """
    user_id = update.effective_user.id
    message_text = update.message.text

    logger.info("message_received", user_id=user_id, text_length=len(message_text))

    try:
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=user_id,
            action="typing",
        )

        # If the user just pressed "Edit" on a plan, inject the original context
        history = context.user_data.get("conversation_history", [])
        edit_context = context.user_data.pop("edit_context", None)
        if edit_context:
            history = history + [
                {"role": "assistant", "content": f"[Previous intent: {edit_context['intent']}] Original request was: {edit_context['original_message']}"}
            ]

        # Dispatch to graph (security checks already done by middleware)
        state_result = await dispatch_message(
            user_id=user_id,
            message_text=message_text,
            conversation_history=history,
        )

        if not state_result:
            await context.bot.send_message(
                chat_id=user_id,
                text="Sorry, something went wrong. Please try again.",
            )
            logger.error("dispatch_returned_none", user_id=user_id)
            return

        # Extract plan from state
        plan = state_result.get("plan", [])
        approval_status = state_result.get("approval_status")

        if approval_status == "pending_approval":
            # Format and send plan with approval buttons
            plan_message = _format_plan_message(plan)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Approve", callback_data="approve"),
                        InlineKeyboardButton("✏️ Edit", callback_data="edit"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
                    ]
                ]
            )

            await context.bot.send_message(
                chat_id=user_id,
                text=plan_message,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

            # Store state for callback
            context.user_data["pending_state"] = state_result

            logger.info("plan_sent_for_approval", user_id=user_id, steps=len(plan))

        elif approval_status == "approved" or approval_status == "completed":
            # Plan was auto-approved or already executed
            result = state_result.get("result", "Task completed.")
            await context.bot.send_message(
                chat_id=user_id,
                text=result,
                parse_mode="Markdown",
            )
            logger.info("task_completed", user_id=user_id)
        else:
            # General response
            response = state_result.get("result", "Done!")
            await context.bot.send_message(
                chat_id=user_id,
                text=response,
                parse_mode="Markdown",
            )

        # Update conversation history — keep a rolling window of 20 messages (10 turns)
        if "conversation_history" not in context.user_data:
            context.user_data["conversation_history"] = []
        history = context.user_data["conversation_history"]
        history.append({"role": "user", "content": message_text})
        if "result" in state_result:
            history.append({"role": "assistant", "content": state_result["result"]})
        # Trim to last 20 messages to prevent context overload
        if len(history) > 20:
            context.user_data["conversation_history"] = history[-20:]

    except Exception as e:
        logger.error("handle_message_error", user_id=user_id, error=str(e))
        await context.bot.send_message(
            chat_id=user_id,
            text="An error occurred. Please try again.",
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline keyboard callbacks for plan approval.

    Args:
        update: Telegram update object with callback query.
        context: Telegram context object.
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    logger.info("callback_received", user_id=user_id, callback=callback_data)

    try:
        # Acknowledge callback
        await query.answer()

        # Get pending state
        pending_state = context.user_data.get("pending_state")
        if not pending_state:
            await query.edit_message_text(text="Request expired. Please send a new message.")
            logger.warning("callback_no_pending_state", user_id=user_id)
            return

        if callback_data == "approve":
            await query.edit_message_text(text="✅ Approved! Executing plan...")

            # Live progress tracking
            steps_log: list[str] = []

            async def on_step(step, success: bool, error):
                icon = "✅" if success else "❌"
                line = f"{icon} *Step {step.step_number}:* {step.description or step.action}"
                if not success and error:
                    line += f"\n  _{error}_"
                steps_log.append(line)
                try:
                    await query.edit_message_text(
                        text="⚙️ *Executing plan...*\n\n" + "\n".join(steps_log),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass  # message may not have changed — Telegram rejects no-op edits

            pending_state["approval_status"] = "approved"
            result = await _execute_approved_plan(pending_state, user_id, progress_callback=on_step)

            await context.bot.send_message(
                chat_id=user_id,
                text=result,
                parse_mode="Markdown",
            )

            logger.info("plan_executed", user_id=user_id)
            context.user_data["pending_state"] = None

        elif callback_data == "edit":
            original_message = pending_state.get("message", "")
            original_intent = pending_state.get("intent", "")
            original_plan = pending_state.get("plan", [])
            plan_lines = "\n".join(f"{i+1}. {s}" for i, s in enumerate(original_plan))
            await query.edit_message_text(
                text=(
                    f"✏️ What would you like to change?\n\n"
                    f"Original request: _{original_message}_\n"
                    f"Intent: {original_intent}\n\n"
                    f"Proposed plan:\n{plan_lines}\n\n"
                    f"Send your updated request and I'll re-plan."
                ),
                parse_mode="Markdown",
            )
            # Keep original context so the next message can build on it
            context.user_data["pending_state"] = None
            context.user_data["edit_context"] = {
                "original_message": original_message,
                "intent": original_intent,
            }
            logger.info("callback_edit_selected", user_id=user_id)

        elif callback_data == "cancel":
            await query.edit_message_text(text="❌ Plan cancelled.")
            context.user_data["pending_state"] = None
            logger.info("callback_cancel_selected", user_id=user_id)

        elif callback_data == "plan_ok":
            await query.edit_message_text(text="Great! Your plan is set. Use /status to track progress.")

        elif callback_data.startswith("rejig_"):
            strategy_map = {
                "rejig_focus": "focus",
                "rejig_quick_wins": "quick_wins",
                "rejig_aggressive": "aggressive",
            }
            strategy = strategy_map.get(callback_data, "focus")
            plan = context.user_data.get("daily_plan")
            if not plan:
                await query.edit_message_text(text="No plan loaded. Run /plan first.")
                return

            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M")
            updated_plan = rejig_day(plan, current_time, strategy)
            context.user_data["daily_plan"] = updated_plan
            await query.edit_message_text(
                text=format_plan_for_telegram(updated_plan),
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error("handle_callback_error", user_id=user_id, error=str(e))
        await query.answer("An error occurred.")


async def handle_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/auth — start Google OAuth2 flow via local redirect."""
    user_id = update.effective_user.id

    if google_auth.is_authenticated():
        await context.bot.send_message(
            chat_id=user_id,
            text="Google is already connected.",
        )
        return

    try:
        url = google_auth.get_auth_url()
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "Click the link below to connect your Google account:\n\n"
                f"{url}\n\n"
                "Your browser will redirect to localhost — the bot will complete auth automatically."
            ),
        )

        # Wait for the callback in the background
        import asyncio
        asyncio.create_task(_complete_auth(context.bot, user_id))

    except Exception as e:
        logger.error("handle_auth_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Failed to start auth flow.")


async def _complete_auth(bot, user_id: int) -> None:
    """Background task: wait for OAuth callback, exchange code, notify user."""
    try:
        code = await google_auth.run_local_auth_server()
        if code:
            google_auth.exchange_code(code)
            await bot.send_message(
                chat_id=user_id,
                text="Google account connected! Calendar and Gmail are now available.",
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text="Auth timed out or was cancelled. Send /auth to try again.",
            )
    except Exception as e:
        logger.error("complete_auth_error", user_id=user_id, error=str(e))
        await bot.send_message(chat_id=user_id, text="Auth failed. Please try /auth again.")


async def handle_authcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/authcode <code> — manual fallback to exchange a Google OAuth2 code."""
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=user_id, text="Usage: /authcode YOUR_CODE")
        return

    code = args[0].strip()
    await context.bot.send_chat_action(chat_id=user_id, action="typing")

    try:
        google_auth.exchange_code(code)
        await context.bot.send_message(
            chat_id=user_id,
            text="Google account connected! Calendar and Gmail are now available.",
        )
    except Exception as e:
        logger.error("handle_authcode_error", user_id=user_id, error=str(e))
        await context.bot.send_message(
            chat_id=user_id,
            text="Failed to exchange code. Try /auth instead.",
        )


async def handle_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/plan — fetch Todoist tasks and show today's time-boxed schedule."""
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action="typing")

    try:
        todos = await todoist_api.get_today_tasks()
        plan = generate_daily_plan(todos)
        context.user_data["daily_plan"] = plan

        # Write start times + durations back to Todoist
        updated, failed = await write_plan_to_todoist(plan)
        sync_note = f"\n\n_Synced {updated} task(s) to Todoist._" if updated else ""

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Looks Good", callback_data="plan_ok"),
            InlineKeyboardButton("Rejig", callback_data="rejig_focus"),
        ]])
        await context.bot.send_message(
            chat_id=user_id,
            text=format_plan_for_telegram(plan) + sync_note,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error("handle_plan_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Could not load your plan. Check your Todoist token.")


async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/add <task> — add a task to Todoist and today's plan."""
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=user_id, text="Usage: /add <task name>")
        return

    content = " ".join(args)
    try:
        task = await todoist_api.add_task(content, due_string="today")

        plan = context.user_data.get("daily_plan")
        if plan:
            success, block = add_task_to_plan(plan, task)
            if success:
                context.user_data["daily_plan"] = plan
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Added *{content}* at {block['start']}–{block['end']}",
                    parse_mode="Markdown",
                )
                return

        await context.bot.send_message(chat_id=user_id, text=f"Added *{content}* to Todoist.", parse_mode="Markdown")
    except Exception as e:
        logger.error("handle_add_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Failed to add task.")


async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/done <task> — mark a task as complete in Todoist and plan."""
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=user_id, text="Usage: /done <task name>")
        return

    name = " ".join(args)
    try:
        task = await todoist_api.find_task_by_name(name)
        if not task:
            await context.bot.send_message(chat_id=user_id, text=f"No task matching '{name}' found.")
            return

        await todoist_api.complete_task(task["id"])

        plan = context.user_data.get("daily_plan")
        if plan:
            mark_task_complete(plan, task["id"])
            context.user_data["daily_plan"] = plan

        await context.bot.send_message(
            chat_id=user_id,
            text=f"Marked *{task['content']}* as done.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("handle_done_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Failed to mark task as done.")


async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/remove <task> — delete a task from Todoist."""
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await context.bot.send_message(chat_id=user_id, text="Usage: /remove <task name>")
        return

    name = " ".join(args)
    try:
        task = await todoist_api.find_task_by_name(name)
        if not task:
            await context.bot.send_message(chat_id=user_id, text=f"No task matching '{name}' found.")
            return

        await todoist_api.delete_task(task["id"])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Removed *{task['content']}*.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("handle_remove_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Failed to remove task.")


async def handle_rejig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/rejig — reorganize the rest of today's plan."""
    user_id = update.effective_user.id
    plan = context.user_data.get("daily_plan")

    if not plan:
        await context.bot.send_message(chat_id=user_id, text="No plan loaded. Run /plan first.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Focus (urgent first)", callback_data="rejig_focus"),
        InlineKeyboardButton("Quick wins", callback_data="rejig_quick_wins"),
        InlineKeyboardButton("Aggressive", callback_data="rejig_aggressive"),
    ]])
    await context.bot.send_message(
        chat_id=user_id,
        text="How would you like to rejig the rest of your day?",
        reply_markup=keyboard,
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — show progress on today's plan."""
    user_id = update.effective_user.id
    plan = context.user_data.get("daily_plan")

    if not plan:
        await context.bot.send_message(chat_id=user_id, text="No plan loaded. Run /plan first.")
        return

    completed = plan.get("completed_tasks", 0)
    total = plan.get("total_tasks", 0)
    rate = plan.get("completion_rate", 0.0)
    pending = len(plan.get("pending", []))

    msg = (
        f"📊 *Today's Progress*\n\n"
        f"✅ Completed: {completed}/{total}\n"
        f"📈 Rate: {rate:.0f}%\n"
        f"📌 Backlog: {pending} tasks"
    )
    await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/profile [key=value ...] — view or update your stored profile."""
    user_id = update.effective_user.id
    args = context.args or []

    from integrations.supabase_profile import get_profile, upsert_profile, format_profile_for_context

    # No args → show current profile
    if not args:
        profile = await get_profile(user_id)
        if not profile:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "No profile saved yet. Set details with:\n"
                    "`/profile name=Your Name timezone=Europe/London`\n"
                    "or add notes like:\n"
                    "`/profile notes=I prefer concise responses`"
                ),
                parse_mode="Markdown",
            )
            return
        text = format_profile_for_context(profile) or "Profile is empty."
        await context.bot.send_message(chat_id=user_id, text=f"```\n{text}\n```", parse_mode="Markdown")
        return

    # Parse key=value pairs — anything not matching goes into notes
    data = {}
    notes_parts = []
    for arg in args:
        if "=" in arg:
            k, _, v = arg.partition("=")
            data[k.strip()] = v.strip()
        else:
            notes_parts.append(arg)
    if notes_parts:
        data["notes"] = " ".join(notes_parts)

    if not data:
        await context.bot.send_message(chat_id=user_id, text="Nothing to update.")
        return

    try:
        await upsert_profile(user_id, data)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Profile updated: {', '.join(f'{k}={v}' for k, v in data.items())}",
        )
    except Exception as e:
        logger.error("handle_profile_error", user_id=user_id, error=str(e))
        await context.bot.send_message(chat_id=user_id, text="Failed to update profile. Check Supabase config.")


def _format_plan_message(plan: list[str]) -> str:
    """
    Format plan as a clean Telegram message.

    Args:
        plan: List of plan steps.

    Returns:
        Formatted message string.
    """
    if not plan:
        return "No plan generated."

    plan_text = "📋 **Proposed Plan:**\n\n"
    for i, step in enumerate(plan, 1):
        plan_text += f"{i}. {step}\n"

    plan_text += (
        "\n\nPlease review and choose:\n"
        "✅ Approve to proceed\n"
        "✏️ Edit to modify\n"
        "❌ Cancel to discard"
    )

    return plan_text


async def _execute_approved_plan(state: dict, user_id: int, progress_callback=None) -> str:
    """Execute an approved plan, optionally streaming step progress via callback."""
    try:
        from dispatcher.graph import execute_plan_node
        result = await execute_plan_node(state, progress_callback=progress_callback)
        logger.info("plan_execution_completed", user_id=user_id)
        return result.get("result", "Plan executed.")
    except Exception as e:
        logger.error("plan_execution_error", user_id=user_id, error=str(e))
        return "Error executing plan. Please try again."
