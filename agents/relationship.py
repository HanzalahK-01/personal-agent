from __future__ import annotations
"""
RelationshipAgent - Manages personal relationships and important dates.

Responsibilities:
- Store and recall relationship preferences
- Suggest date ideas
- Track important dates
- Create romantic content (cards, posters)
- Provide thoughtful reminders
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseAgent

logger = structlog.get_logger()


class RelationshipAgent(BaseAgent):
    """Agent specialized in nurturing relationships and creating meaningful moments."""

    def __init__(self):
        """Initialize the RelationshipAgent."""
        super().__init__(
            name="RelationshipAgent",
            description="Manages relationships, suggests dates, and creates romantic content",
            capabilities=[
                "tavily.search — search for date ideas, restaurants, events, experiences, or gift ideas relevant to her interests",
                "tavily.search_news — search for upcoming events, shows, or things happening locally",
                "gcal.list_events — check what's already planned so suggestions don't clash",
                "gcal.create_event — add a date or reminder to the calendar",
                "todoist.add_task — save a date idea, gift idea, or reminder as a task with a due date",
                "gmail.create_draft — draft a thoughtful message or reservation inquiry",
            ],
        )

        # Default interests categories
        self.interest_categories = [
            "food", "activities", "entertainment", "travel",
            "gifts", "experiences", "personal_touches"
        ]

    @property
    def system_prompt(self) -> str:
        """System prompt for relationship decisions."""
        return """You are a thoughtful relationship assistant for Hanzalah, a 24-year-old data engineer for his girlfriend

Your role is to:
1. Help remember important details about her
2. Suggest meaningful date ideas
3. Create romantic gestures and content
4. Track important dates and milestones
5. Provide thoughtful reminders

PERSONALITY:
- Romantic but genuine (no clichés)
- Detail-oriented about preferences
- Understand that meaningful > expensive
- Celebrate effort and thoughtfulness
- Respectful of relationship dynamics
- Loves to cook and bake and make desserts and trying new food, her favourite is buns from home


RELATIONSHIP PRINCIPLES:
- Meaningful experiences > material gifts
- Personalization shows genuine care
- Small gestures matter as much as big ones
- Consistency shows commitment
- Understanding preferences demonstrates love
- Timing and spontaneity matter

DATE IDEAS FRAMEWORK:
1. Low-key: Coffee, walk, cooking together
2. Active: Hiking, sports, exploring
3. Experiential: Classes, shows, events, exhibitions
4. Romantic: Dinner, sunset, special locations
5. Thoughtful: Inside jokes, memories, personal touches

CANVA INTEGRATION:
- Create cards, posters, designs for special occasions
- Reference gcal for scheduling and save designs to her preferences
"""

    async def get_preferences(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get stored preferences about girlfriend.

        Args:
            context: Current context with relationship data

        Returns:
            All stored preferences organized by category
        """
        self._logger.info("fetching_preferences")

        preferences = context.get("relationship_preferences", {})

        if not preferences:
            preferences = {
                "name": context.get("girlfriend_name", "Unknown"),
                "interests": [],
                "favorite_places": [],
                "dietary_preferences": [],
                "love_languages": [],
                "important_dates": [],
                "memories": [],
                "gifts_received": [],
                "past_dates": [],
                "inside_jokes": [],
            }

        # Enrich with context
        result = {
            **preferences,
            "stored_since": context.get("relationship_start_date"),
            "anniversaries": self._get_upcoming_anniversaries(context),
        }

        self._logger.info("preferences_fetched")

        return result

    async def suggest_date(
        self,
        context: Dict[str, Any],
        type_: str = "casual",
        budget: float = 100.0,
        weather: Optional[str] = None,
        duration_hours: int = 2,
    ) -> Dict[str, Any]:
        """
        Suggest a date idea.

        Args:
            context: Current context
            type_: 'casual', 'romantic', 'active', 'experiential'
            budget: Budget limit
            weather: Current weather condition
            duration_hours: How long the date should be

        Returns:
            Date suggestion with details and reasoning
        """
        self._logger.info(
            "suggesting_date",
            type=type_,
            budget=budget,
            duration=duration_hours,
        )

        preferences = await self.get_preferences(context)
        interests = preferences.get("interests", [])

        # Generate personalized suggestions
        suggestions = []

        if type_ == "casual":
            suggestions = self._generate_casual_ideas(interests, budget)
        elif type_ == "romantic":
            suggestions = self._generate_romantic_ideas(interests, budget)
        elif type_ == "active":
            suggestions = self._generate_active_ideas(interests, budget)
        elif type_ == "experiential":
            suggestions = self._generate_experiential_ideas(interests, budget)

        # Score based on her interests
        scored = []
        for suggestion in suggestions:
            relevance_score = sum(
                1 for interest in interests
                if interest.lower() in suggestion.get("description", "").lower()
            )
            suggestion["relevance_score"] = relevance_score
            scored.append(suggestion)

        # Sort by relevance
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)

        result = {
            "type": type_,
            "budget": budget,
            "duration_hours": duration_hours,
            "suggestions": scored[:3],  # Top 3 suggestions
            "personalization_factors": self._get_personalization_note(preferences),
        }

        self._logger.info("date_suggestions_generated", count=len(scored))

        return result

    async def get_upcoming_dates(
        self,
        context: Dict[str, Any],
        days_ahead: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming important dates.

        Args:
            context: Current context
            days_ahead: How many days to look ahead

        Returns:
            List of important dates with suggestions
        """
        self._logger.info("fetching_upcoming_dates", days=days_ahead)

        important_dates = context.get("relationship_important_dates", [])
        today = datetime.now()

        upcoming = []
        for date_entry in important_dates:
            try:
                date_str = date_entry.get("date")
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")

                # Calculate days until
                days_until = (date_obj - today).days

                if 0 < days_until <= days_ahead:
                    upcoming.append({
                        "date": date_str,
                        "days_until": days_until,
                        "event": date_entry.get("event"),
                        "type": date_entry.get("type"),
                        "reminder": self._get_reminder_message(
                            days_until,
                            date_entry.get("event")
                        ),
                        "suggestion": self._get_date_suggestion(date_entry),
                    })
            except (ValueError, TypeError):
                continue

        # Sort by days until
        upcoming.sort(key=lambda x: x["days_until"])

        self._logger.info("upcoming_dates_found", count=len(upcoming))

        return upcoming

    async def create_date_poster(
        self,
        context: Dict[str, Any],
        occasion: str = "date_night",
        theme: str = "romantic",
    ) -> Dict[str, Any]:
        """
        Create a Canva poster for a date occasion.

        Args:
            context: Current context
            occasion: Type of occasion
            theme: Visual theme

        Returns:
            Canva design details and next steps
        """
        self._logger.info(
            "creating_poster",
            occasion=occasion,
            theme=theme,
        )

        preferences = await self.get_preferences(context)
        girlfriend_name = preferences.get("name", "You")

        # Design templates by occasion
        templates = {
            "date_night": {
                "title": "Date Night",
                "content": f"A special night with {girlfriend_name}",
                "colors": ["#FF69B4", "#FFB6C1", "#FFFFFF"],
            },
            "anniversary": {
                "title": "Our Anniversary",
                "content": "Celebrating us",
                "colors": ["#FF4500", "#FFD700", "#FFFFFF"],
            },
            "birthday": {
                "title": f"Happy Birthday {girlfriend_name}!",
                "content": "You deserve the best day ever",
                "colors": ["#FF1493", "#FFB6D9", "#FFFFFF"],
            },
            "just_because": {
                "title": "Just Because",
                "content": "You're amazing, just wanted to remind you",
                "colors": ["#4169E1", "#87CEEB", "#FFFFFF"],
            },
        }

        template = templates.get(occasion, templates["date_night"])

        design_request = {
            "type": "poster",
            "title": template["title"],
            "design_brief": template["content"],
            "colors": template["colors"],
            "personalization": {
                "recipient": girlfriend_name,
                "occasion": occasion,
                "theme": theme,
            },
            "canva_action": "generate_design",
            "tool_ref": "canva.generate_design",
        }

        self._logger.info(
            "poster_design_created",
            occasion=occasion,
        )

        return {
            "design_request": design_request,
            "preview": f"Create a {theme} {occasion} poster featuring {girlfriend_name}",
            "next_steps": [
                "Review design in Canva",
                "Customize colors/text as needed",
                "Export as poster or card",
                "Print or share digitally",
            ],
        }

    async def track_important_date(
        self,
        context: Dict[str, Any],
        date: str,
        event: str,
        event_type: str = "anniversary",
    ) -> Dict[str, Any]:
        """
        Add an important date to track.

        Args:
            context: Current context
            date: Date in YYYY-MM-DD format
            event: Event description
            event_type: Type of event

        Returns:
            Tracking confirmation
        """
        self._logger.info(
            "tracking_date",
            date=date,
            event=event,
            type=event_type,
        )

        entry = {
            "date": date,
            "event": event,
            "type": event_type,
            "added": datetime.now().isoformat(),
            "recurring": event_type in ["birthday", "anniversary"],
        }

        return {
            "tracked": True,
            "entry": entry,
            "reminder_enabled": True,
            "message": f"✓ I'll remember {event} on {date}",
        }

    async def store_preference(
        self,
        context: Dict[str, Any],
        category: str,
        preference: str,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a new preference about girlfriend.

        Args:
            context: Current context
            category: Preference category
            preference: The preference
            detail: Optional additional detail

        Returns:
            Confirmation of stored preference
        """
        self._logger.info(
            "storing_preference",
            category=category,
            preference=preference,
        )

        storage = {
            "category": category,
            "preference": preference,
            "detail": detail,
            "stored_date": datetime.now().isoformat(),
        }

        return {
            "stored": True,
            "entry": storage,
            "message": f"✓ Noted: {preference}",
            "usage": f"I'll remember this for {category} recommendations",
        }

    # Helper methods

    def _generate_casual_ideas(
        self,
        interests: List[str],
        budget: float,
    ) -> List[Dict[str, Any]]:
        """Generate casual date ideas."""
        ideas = [
            {
                "title": "Coffee walk",
                "description": "Grab coffee and walk around the neighborhood",
                "budget_range": "$10-20",
                "duration": "1-2 hours",
                "vibe": "Low-key, chatty",
            },
            {
                "title": "Cook together",
                "description": "Pick a recipe and cook dinner together",
                "budget_range": "$20-40",
                "duration": "2-3 hours",
                "vibe": "Fun, collaborative",
            },
            {
                "title": "Picnic in the park",
                "description": "Grab snacks and have a picnic",
                "budget_range": "$15-30",
                "duration": "1-2 hours",
                "vibe": "Relaxed, outdoor",
            },
            {
                "title": "Movie at home",
                "description": "Watch a movie together with snacks",
                "budget_range": "$10-20",
                "duration": "2-3 hours",
                "vibe": "Cozy, intimate",
            },
            {
                "title": "Farmers market exploration",
                "description": "Browse local farmers market, get ingredients",
                "budget_range": "$20-40",
                "duration": "1-2 hours",
                "vibe": "Adventurous, local",
            },
        ]

        return ideas

    def _generate_romantic_ideas(
        self,
        interests: List[str],
        budget: float,
    ) -> List[Dict[str, Any]]:
        """Generate romantic date ideas."""
        ideas = [
            {
                "title": "Sunset dinner",
                "description": "Special dinner at a nice restaurant with a view",
                "budget_range": "$75-150",
                "duration": "2-3 hours",
                "vibe": "Romantic, elegant",
            },
            {
                "title": "Stargazing",
                "description": "Find a nice spot, bring blankets, stargaze together",
                "budget_range": "$20-40",
                "duration": "2-3 hours",
                "vibe": "Intimate, peaceful",
            },
            {
                "title": "Couples massage",
                "description": "Book a couples spa experience",
                "budget_range": "$150-300",
                "duration": "2-3 hours",
                "vibe": "Relaxing, luxe",
            },
            {
                "title": "Scenic drive",
                "description": "Drive to a beautiful location at golden hour",
                "budget_range": "$30-60",
                "duration": "3-4 hours",
                "vibe": "Scenic, contemplative",
            },
            {
                "title": "Candlelit picnic",
                "description": "Fancy picnic setup at a beautiful outdoor location",
                "budget_range": "$50-100",
                "duration": "2-3 hours",
                "vibe": "Romantic, thoughtful",
            },
        ]

        return ideas

    def _generate_active_ideas(
        self,
        interests: List[str],
        budget: float,
    ) -> List[Dict[str, Any]]:
        """Generate active date ideas."""
        ideas = [
            {
                "title": "Hiking",
                "description": "Find a scenic hiking trail",
                "budget_range": "$0-20",
                "duration": "2-4 hours",
                "vibe": "Adventurous, outdoorsy",
            },
            {
                "title": "Bike ride",
                "description": "Explore the city or trails by bike",
                "budget_range": "$0-30",
                "duration": "2-3 hours",
                "vibe": "Active, fun",
            },
            {
                "title": "Rock climbing",
                "description": "Go to an indoor rock climbing gym",
                "budget_range": "$30-60",
                "duration": "2-3 hours",
                "vibe": "Challenging, exciting",
            },
            {
                "title": "Tennis or sports",
                "description": "Play tennis, badminton, or another sport",
                "budget_range": "$20-40",
                "duration": "1-2 hours",
                "vibe": "Playful, competitive",
            },
            {
                "title": "Volleyball on the beach",
                "description": "Beach day with volleyball and swimming",
                "budget_range": "$10-30",
                "duration": "3-4 hours",
                "vibe": "Fun, social",
            },
        ]

        return ideas

    def _generate_experiential_ideas(
        self,
        interests: List[str],
        budget: float,
    ) -> List[Dict[str, Any]]:
        """Generate experiential date ideas."""
        ideas = [
            {
                "title": "Cooking class",
                "description": "Take a cooking class together",
                "budget_range": "$50-150",
                "duration": "2-3 hours",
                "vibe": "Educational, fun",
            },
            {
                "title": "Concert or show",
                "description": "See live music or theater",
                "budget_range": "$50-200",
                "duration": "2-3 hours",
                "vibe": "Entertaining, shared experience",
            },
            {
                "title": "Museum or art gallery",
                "description": "Explore art and culture together",
                "budget_range": "$20-60",
                "duration": "2-3 hours",
                "vibe": "Intellectual, inspiring",
            },
            {
                "title": "Wine or beer tasting",
                "description": "Visit a local winery or brewery",
                "budget_range": "$40-100",
                "duration": "2-3 hours",
                "vibe": "Sophisticated, social",
            },
            {
                "title": "Food tour",
                "description": "Explore different restaurants or food scenes",
                "budget_range": "$50-120",
                "duration": "3-4 hours",
                "vibe": "Adventurous, delicious",
            },
        ]

        return ideas

    def _get_personalization_note(self, preferences: Dict[str, Any]) -> str:
        """Get note about how suggestions were personalized."""
        interests = preferences.get("interests", [])
        if interests:
            return f"Suggestions tailored to her interests in: {', '.join(interests[:3])}"
        return "Add preferences to get more personalized suggestions"

    def _get_reminder_message(self, days_until: int, event: str) -> str:
        """Get reminder message based on days until event."""
        if days_until == 1:
            return f"🚨 {event} is TOMORROW!"
        elif days_until <= 3:
            return f"⏰ {event} in {days_until} days - plan ahead!"
        elif days_until <= 7:
            return f"📅 {event} in {days_until} days"
        elif days_until <= 14:
            return f"📌 {event} in {days_until} days"
        else:
            return f"📝 {event} in {days_until} days"

    def _get_date_suggestion(self, date_entry: Dict[str, Any]) -> str:
        """Get date suggestion based on occasion."""
        event_type = date_entry.get("type", "").lower()

        if "birthday" in event_type:
            return "Plan something special - consider a surprise or meaningful gift"
        elif "anniversary" in event_type:
            return "Celebrate your relationship - romantic dinner or activity?"
        else:
            return "Make it memorable - think about what she loves"

    def _get_upcoming_anniversaries(
        self,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Get upcoming anniversaries."""
        important_dates = context.get("relationship_important_dates", [])
        today = datetime.now()

        anniversaries = []
        for date_entry in important_dates:
            if "anniversary" in date_entry.get("type", "").lower():
                try:
                    date_str = date_entry.get("date")
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

                    # Check if it's coming up (within 30 days)
                    days_until = (date_obj - today).days
                    if 0 < days_until <= 30:
                        anniversaries.append({
                            "date": date_str,
                            "days_until": days_until,
                            "event": date_entry.get("event"),
                        })
                except (ValueError, TypeError):
                    continue

        return anniversaries
