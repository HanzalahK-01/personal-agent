from __future__ import annotations
"""
InboxAgent - Manages email triage and communication.

Responsibilities:
- Read and process emails
- Prioritize by urgency and importance
- Summarize email content
- Draft reply suggestions
- Manage unread email counts
"""

import re
import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAgent

logger = structlog.get_logger()


class InboxAgent(BaseAgent):
    """Agent specialized in email management and communication triage."""

    def __init__(self):
        """Initialize the InboxAgent."""
        super().__init__(
            name="InboxAgent",
            description="Manages email inbox, prioritizes messages, and drafts replies",
            capabilities=[
                "gmail.search_messages — search for emails by sender, subject, or keyword (e.g. query='from:boss is:unread')",
                "gmail.read_message — read the full body of a specific email by message ID",
                "gmail.read_thread — read a full email thread by thread ID",
                "gmail.create_draft — compose a new email or reply draft (to, subject, body)",
                "todoist.add_task — create a follow-up task from an email action item",
            ],
        )
        # Priority keywords
        self.urgent_keywords = [
            "urgent", "asap", "critical", "emergency", "immediate",
            "action required", "deadline", "important", "please reply"
        ]
        self.work_keywords = [
            "meeting", "project", "deliverable", "status", "update",
            "review", "feedback", "presentation", "standup"
        ]
        self.personal_keywords = [
            "personal", "family", "health", "birthday", "anniversary"
        ]

    @property
    def system_prompt(self) -> str:
        """System prompt for email communication decisions."""
        return """You are an email management assistant for Hanzalah, a 24-year-old data engineer.

Your role is to:
1. Triage incoming emails by urgency and importance
2. Identify action items and deadlines
3. Summarize long emails concisely
4. Draft professional replies when needed
5. Help manage inbox overload

PERSONALITY:
- Concise and direct communication style
- Respectful of Hanzalah's time
- Professional but personable
- Detail-oriented about deadlines

EMAIL CATEGORIES:
1. URGENT: Requires immediate action (deadlines within 24h, critical issues)
2. IMPORTANT: Business-critical but not immediately urgent
3. FYI: Informational, no action needed
4. FOLLOW-UP: Requires response but not urgent
5. SPAM: Promotional or low-value

RESPONSE STYLE:
- Provide specific, actionable email summaries
- Highlight deadlines and blockers
- Suggest next steps for action items
- Flag emails that need responses
- Maintain professional tone in drafts
"""

    async def get_unread_emails(
        self,
        context: Dict[str, Any],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get unread emails from inbox.

        Args:
            context: Current context with email state
            limit: Maximum emails to return

        Returns:
            List of unread emails with metadata
        """
        self._logger.info("fetching_unread_emails", limit=limit)

        emails = context.get("emails", [])
        unread = [e for e in emails if not e.get("read")]

        # Sort by date (newest first)
        unread.sort(
            key=lambda e: e.get("received_time", ""),
            reverse=True
        )

        result = unread[:limit]

        self._logger.info("unread_emails_fetched", count=len(result))

        return result

    async def search_emails(
        self,
        context: Dict[str, Any],
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search emails by query.

        Args:
            context: Current context
            query: Search query (sender, subject, keywords)
            limit: Max results

        Returns:
            Matching emails
        """
        self._logger.info("searching_emails", query=query)

        emails = context.get("emails", [])
        query_lower = query.lower()

        matching = [
            e for e in emails
            if (
                query_lower in e.get("subject", "").lower()
                or query_lower in e.get("sender", "").lower()
                or query_lower in e.get("body", "").lower()
                or query_lower in e.get("body_preview", "").lower()
            )
        ]

        result = matching[:limit]
        self._logger.info("search_results", count=len(result))

        return result

    async def prioritize_emails(
        self,
        context: Dict[str, Any],
        emails: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Categorize and prioritize emails by urgency.

        Args:
            context: Current context
            emails: List of emails to prioritize (uses unread if None)

        Returns:
            Emails organized by priority tier
        """
        if emails is None:
            emails = await self.get_unread_emails(context)

        self._logger.info("prioritizing_emails", email_count=len(emails))

        prioritized = {
            "urgent": [],
            "important": [],
            "action_required": [],
            "fyi": [],
            "spam": [],
        }

        for email in emails:
            priority = self._calculate_priority(email)
            prioritized[priority].append(email)

        self._logger.info(
            "emails_prioritized",
            urgent=len(prioritized["urgent"]),
            important=len(prioritized["important"]),
            action=len(prioritized["action_required"]),
        )

        return prioritized

    async def summarize_email(
        self,
        email: Dict[str, Any],
        include_action_items: bool = True,
    ) -> Dict[str, Any]:
        """
        Summarize an email's content.

        Args:
            email: Email to summarize
            include_action_items: Whether to extract action items

        Returns:
            Email summary with key points and action items
        """
        self._logger.info(
            "summarizing_email",
            sender=email.get("sender", "unknown"),
        )

        body = email.get("body", email.get("body_preview", ""))

        # Extract key sentences (first and important ones)
        sentences = [s.strip() for s in body.split(".") if s.strip()]
        key_points = sentences[:3]  # First 3 sentences as summary

        # Extract action items
        action_items = []
        if include_action_items:
            action_items = self._extract_action_items(body)

        # Extract deadline if mentioned
        deadline = self._extract_deadline(body)

        summary = {
            "from": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "received": email.get("received_time", ""),
            "key_points": key_points,
            "action_items": action_items,
            "deadline": deadline,
            "requires_response": self._needs_response(email),
            "priority": self._calculate_priority(email),
            "length_words": len(body.split()),
        }

        self._logger.info(
            "email_summarized",
            action_items_count=len(action_items),
            requires_response=summary["requires_response"],
        )

        return summary

    async def draft_reply(
        self,
        email: Dict[str, Any],
        reply_type: str = "professional",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Draft a reply to an email.

        Args:
            email: Email to reply to
            reply_type: Style (professional, casual, grateful, confirm)
            context: Optional context for personalization

        Returns:
            Suggested reply text
        """
        sender_name = self._extract_name(email.get("sender", ""))
        subject = email.get("subject", "")

        self._logger.info(
            "drafting_reply",
            to=sender_name,
            type=reply_type,
        )

        # Determine what type of reply is needed
        action_items = self._extract_action_items(
            email.get("body", email.get("body_preview", ""))
        )

        if reply_type == "professional":
            reply = self._draft_professional_reply(
                sender_name,
                action_items,
            )
        elif reply_type == "casual":
            reply = self._draft_casual_reply(sender_name)
        elif reply_type == "grateful":
            reply = self._draft_grateful_reply(sender_name)
        elif reply_type == "confirm":
            reply = self._draft_confirmation_reply(sender_name, action_items)
        else:
            reply = f"Hi {sender_name},\n\nThanks for reaching out.\n\nBest regards,\nHanzalah"

        self._logger.info("reply_drafted")

        return reply

    async def find_action_items(
        self,
        context: Dict[str, Any],
        emails: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract all action items from emails.

        Args:
            context: Current context
            emails: Specific emails to search (uses unread if None)

        Returns:
            List of action items with sources
        """
        if emails is None:
            emails = await self.get_unread_emails(context, limit=30)

        self._logger.info("finding_action_items", email_count=len(emails))

        all_actions = []

        for email in emails:
            actions = self._extract_action_items(
                email.get("body", email.get("body_preview", ""))
            )

            for action in actions:
                all_actions.append({
                    "item": action,
                    "from": email.get("sender", ""),
                    "subject": email.get("subject", ""),
                    "deadline": self._extract_deadline(
                        email.get("body", "")
                    ),
                    "priority": self._calculate_priority(email),
                })

        all_actions.sort(
            key=lambda a: (
                a["priority"] == "urgent",
                a["deadline"] is not None,
            ),
            reverse=True
        )

        self._logger.info("action_items_extracted", count=len(all_actions))

        return all_actions

    # Helper methods

    def _calculate_priority(self, email: Dict[str, Any]) -> str:
        """Calculate email priority based on various signals."""
        body = (email.get("body", "") + email.get("subject", "")).lower()
        sender = email.get("sender", "").lower()

        # Check for spam indicators
        if self._is_spam(email):
            return "spam"

        # Check for urgent keywords
        if any(keyword in body for keyword in self.urgent_keywords):
            return "urgent"

        # Check if sender is important (manager, colleague)
        if any(domain in sender for domain in ["boss", "manager", "founder"]):
            return "important"

        # Check for work-related keywords
        if any(keyword in body for keyword in self.work_keywords):
            return "important"

        # Check if personal
        if any(keyword in body for keyword in self.personal_keywords):
            return "action_required"

        # Check if needs response
        if self._needs_response(email):
            return "action_required"

        # Default to FYI
        return "fyi"

    def _is_spam(self, email: Dict[str, Any]) -> bool:
        """Detect if email is likely spam."""
        subject = email.get("subject", "").lower()
        sender = email.get("sender", "").lower()
        body = email.get("body", email.get("body_preview", "")).lower()

        spam_indicators = [
            "unsubscribe",
            "promotional",
            "limited time",
            "click here",
            "verify account",
            "confirm password",
        ]

        return any(indicator in (subject + body) for indicator in spam_indicators)

    def _needs_response(self, email: Dict[str, Any]) -> bool:
        """Determine if email needs a response."""
        body = (email.get("body", "") + email.get("subject", "")).lower()

        response_triggers = [
            "please reply",
            "let me know",
            "thoughts?",
            "feedback?",
            "when are you available",
            "what do you think",
            "can you",
            "question:",
            "?",  # Has question mark
        ]

        return any(trigger in body for trigger in response_triggers)

    def _extract_action_items(self, text: str) -> List[str]:
        """Extract action items from email text."""
        if not text:
            return []

        action_patterns = [
            r"(?:please|can you|could you|need to|should|will you).*?(?:\.|:)",
            r"(?:ACTION|TODO|TASK)[\s:]*([^.\n]+)",
            r"(?:to do|to-do)[\s:]*([^.\n]+)",
        ]

        actions = []
        text_lower = text.lower()

        for pattern in action_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            actions.extend(matches)

        # Clean up duplicates and short phrases
        actions = list(set(actions))
        actions = [a.strip() for a in actions if len(a.strip()) > 10]

        return actions[:5]  # Return top 5 action items

    def _extract_deadline(self, text: str) -> Optional[str]:
        """Extract deadline from email text."""
        if not text:
            return None

        deadline_patterns = [
            r"by\s+(\w+\s+\d{1,2})",
            r"deadline\s*:\s*(\w+\s+\d{1,2})",
            r"before\s+(\w+\s+\d{1,2})",
            r"due\s+(\w+\s+\d{1,2})",
            r"(\w+\s+\d{1,2}th)",
        ]

        for pattern in deadline_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_name(self, email_address: str) -> str:
        """Extract person's name from email address."""
        if "<" in email_address:
            # Format: "John Doe <john@example.com>"
            return email_address.split("<")[0].strip()

        # Extract from email address
        local_part = email_address.split("@")[0]
        # Convert john.doe or johndoe to John Doe
        name = " ".join(local_part.split("."))
        return name.capitalize()

    def _draft_professional_reply(
        self,
        sender_name: str,
        action_items: List[str],
    ) -> str:
        """Draft a professional reply."""
        reply = f"Hi {sender_name},\n\n"

        if action_items:
            reply += "Thanks for your message. I'll take care of the following:\n\n"
            for i, item in enumerate(action_items[:3], 1):
                reply += f"{i}. {item}\n"
            reply += "\nI'll follow up with you soon.\n\n"
        else:
            reply += "Thank you for reaching out. I'll review this and get back to you.\n\n"

        reply += "Best regards,\nHanzalah"

        return reply

    def _draft_casual_reply(self, sender_name: str) -> str:
        """Draft a casual reply."""
        return (
            f"Hey {sender_name},\n\n"
            "Thanks for the message! Let me get back to you on this.\n\n"
            "Talk soon,\nHanzalah"
        )

    def _draft_grateful_reply(self, sender_name: str) -> str:
        """Draft a grateful reply."""
        return (
            f"Hi {sender_name},\n\n"
            "Thank you so much for this! I really appreciate it.\n\n"
            "Best,\nHanzalah"
        )

    def _draft_confirmation_reply(
        self,
        sender_name: str,
        action_items: List[str],
    ) -> str:
        """Draft a confirmation reply."""
        reply = f"Hi {sender_name},\n\n"
        reply += "Got it! Confirming that I'll:\n\n"

        for i, item in enumerate(action_items[:3], 1):
            reply += f"✓ {item}\n"

        reply += "\nI'll keep you posted on progress.\n\n"
        reply += "Thanks,\nHanzalah"

        return reply
