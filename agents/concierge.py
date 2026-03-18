from __future__ import annotations
"""
ConciergeAgent - Discovers local events, restaurants, and activities.

Responsibilities:
- Search for events and activities
- Find and recommend restaurants
- Discover entertainment options
- Save recommendations for later
- Handle booking logistics
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseAgent

logger = structlog.get_logger()


class ConciergeAgent(BaseAgent):
    """Agent specialized in local discovery and booking logistics."""

    def __init__(self):
        """Initialize the ConciergeAgent."""
        super().__init__(
            name="ConciergeAgent",
            description="Discovers events, restaurants, activities, and handles bookings",
            capabilities=[
                "tavily.search — search the web for events, restaurants, activities, reviews, or any local discovery",
                "tavily.search_news — search for news or trending topics",
                "gcal.list_events — check what's already in the calendar",
                "gcal.create_event — add a confirmed booking or reservation to the calendar",
                "todoist.add_task — save a recommendation or follow-up action as a Todoist task",
                "gmail.create_draft — draft an email (e.g. reservation inquiry)",
            ],
        )

    @property
    def system_prompt(self) -> str:
        """System prompt for concierge decisions."""
        return """You are a personal concierge for Hanzalah, a 24-year-old data engineer in a startup.

Your role is to:
1. Discover local events, restaurants, and activities
2. Find unique and interesting experiences
3. Handle booking logistics and reservations
4. Curate recommendations based on preferences
5. Save options for future reference

PERSONALITY:
- Helpful and resourceful
- Know the local scene well
- Balance popular vs. hidden gems
- Understand value and quality
- Detail-oriented on logistics

DISCOVERY FRAMEWORK:
- Events: concerts, shows, festivals, sports
- Restaurants: fine dining, casual, cuisine-specific, trending
- Activities: fitness, entertainment, experiences, outdoor
- Venues: bars, cafes, rooftop spots, scenic locations

RECOMMENDATION LOGIC:
- Consider time availability
- Factor in budget
- Match personality/interests
- Provide logistics (hours, location, reservation needed)
- Give insider tips when available

BOOKING ASSISTANCE:
- Verify availability
- Confirm requirements (party size, payment)
- Get confirmation details
- Add to calendar when booked
"""

    async def search_events(
        self,
        context: Dict[str, Any],
        query: str,
        date_range: Optional[tuple] = None,
        category: str = "all",
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for upcoming events.

        Args:
            context: Current context
            query: Search query (location, keyword)
            date_range: Tuple of (start_date, end_date)
            category: Event category filter
            max_results: Maximum results to return

        Returns:
            List of matching events with details
        """
        self._logger.info(
            "searching_events",
            query=query,
            category=category,
        )

        # Use brave/web search via MCP
        # Simulating results based on context
        results = self._generate_event_results(
            query,
            category,
            max_results,
        )

        # Filter by date range if provided
        if date_range:
            start, end = date_range
            results = [
                r for r in results
                if self._is_within_date_range(r.get("date"), start, end)
            ]

        self._logger.info("events_found", count=len(results))

        return {
            "query": query,
            "category": category,
            "results": results,
            "search_date": datetime.now().isoformat(),
            "tips": self._get_search_tips(category),
        }

    async def find_restaurants(
        self,
        context: Dict[str, Any],
        query: Optional[str] = None,
        cuisine: Optional[str] = None,
        price_range: str = "moderate",
        party_size: int = 2,
        date: Optional[str] = None,
        time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Find restaurants with availability.

        Args:
            context: Current context
            query: Search query (name, location)
            cuisine: Cuisine type filter
            price_range: 'budget', 'moderate', 'upscale', 'fine'
            party_size: Number of people
            date: Preferred date
            time: Preferred time

        Returns:
            List of restaurants with availability
        """
        self._logger.info(
            "finding_restaurants",
            cuisine=cuisine,
            price_range=price_range,
            party_size=party_size,
        )

        restaurants = self._generate_restaurant_results(
            cuisine,
            price_range,
            party_size,
        )

        # Check availability
        for restaurant in restaurants:
            if date and time:
                availability = self._check_restaurant_availability(
                    restaurant,
                    date,
                    time,
                    party_size,
                )
                restaurant["availability"] = availability
                restaurant["available"] = availability["has_availability"]
            else:
                restaurant["available"] = True
                restaurant["availability"] = {"has_availability": True}

        # Sort available first, then by rating
        restaurants.sort(
            key=lambda r: (
                not r.get("available"),
                -float(r.get("rating", 0)),
            )
        )

        self._logger.info("restaurants_found", count=len(restaurants))

        return {
            "query": query,
            "cuisine": cuisine,
            "price_range": price_range,
            "party_size": party_size,
            "results": restaurants[:10],
            "search_date": datetime.now().isoformat(),
            "tips": self._get_restaurant_tips(price_range),
        }

    async def discover_activities(
        self,
        context: Dict[str, Any],
        category: str = "all",
        duration_minutes: int = 120,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Discover local activities and experiences.

        Args:
            context: Current context
            category: Activity category
            duration_minutes: Duration preference
            max_results: Maximum results

        Returns:
            List of activity ideas
        """
        self._logger.info(
            "discovering_activities",
            category=category,
            duration=duration_minutes,
        )

        activities = self._generate_activity_results(
            category,
            duration_minutes,
        )

        self._logger.info("activities_found", count=len(activities))

        return {
            "category": category,
            "duration_preference": f"{duration_minutes} minutes",
            "results": activities[:max_results],
            "tips": self._get_activity_tips(category),
            "discovery_date": datetime.now().isoformat(),
        }

    async def save_recommendation(
        self,
        context: Dict[str, Any],
        name: str,
        item_type: str,
        details: Dict[str, Any],
        category: str = "general",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Save a recommendation for later.

        Args:
            context: Current context
            name: Recommendation name
            item_type: Type (restaurant, event, activity, venue)
            details: Item details (address, hours, cost, etc.)
            category: Categorization
            notes: Personal notes

        Returns:
            Saved recommendation
        """
        self._logger.info(
            "saving_recommendation",
            name=name,
            type=item_type,
        )

        recommendation = {
            "id": self._generate_rec_id(),
            "name": name,
            "type": item_type,
            "category": category,
            "details": details,
            "notes": notes,
            "saved_date": datetime.now().isoformat(),
            "status": "saved",
            "visited": False,
        }

        self._logger.info("recommendation_saved", name=name)

        return {
            "saved": True,
            "recommendation": recommendation,
            "message": f"✓ Saved: {name}",
        }

    async def get_recommendations(
        self,
        context: Dict[str, Any],
        category: Optional[str] = None,
        item_type: Optional[str] = None,
        visited: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get saved recommendations.

        Args:
            context: Current context
            category: Filter by category
            item_type: Filter by type
            visited: Whether to show visited items

        Returns:
            List of saved recommendations
        """
        self._logger.info(
            "fetching_recommendations",
            category=category,
            type=item_type,
        )

        recommendations = context.get("saved_recommendations", [])

        # Filter
        filtered = recommendations
        if category:
            filtered = [r for r in filtered if r.get("category") == category]
        if item_type:
            filtered = [r for r in filtered if r.get("type") == item_type]

        filtered = [r for r in filtered if r.get("visited") == visited]

        self._logger.info("recommendations_fetched", count=len(filtered))

        return filtered

    async def book_reservation(
        self,
        context: Dict[str, Any],
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
        name: str = "Hanzalah",
        phone: Optional[str] = None,
        special_requests: str = "",
    ) -> Dict[str, Any]:
        """
        Book a restaurant reservation.

        Args:
            context: Current context
            restaurant_id: ID of restaurant
            date: Date in YYYY-MM-DD format
            time: Time in HH:MM format
            party_size: Number of guests
            name: Name for reservation
            phone: Contact phone
            special_requests: Special requests/notes

        Returns:
            Booking confirmation
        """
        self._logger.info(
            "booking_reservation",
            restaurant=restaurant_id,
            date=date,
            party_size=party_size,
        )

        # Simulate booking
        confirmation = {
            "id": self._generate_booking_id(),
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "name": name,
            "phone": phone,
            "special_requests": special_requests,
            "confirmed_date": datetime.now().isoformat(),
            "status": "confirmed",
            "confirmation_number": f"RES{self._generate_booking_id()}",
        }

        self._logger.info(
            "reservation_booked",
            confirmation=confirmation["confirmation_number"],
        )

        return {
            "booked": True,
            "confirmation": confirmation,
            "next_steps": [
                f"Confirmation #{confirmation['confirmation_number']}",
                f"Date: {date} at {time}",
                "Arrive 10-15 minutes early",
                "Add to calendar",
            ],
        }

    async def search_web(
        self,
        context: Dict[str, Any],
        query: str,
        category: str = "restaurants",
    ) -> Dict[str, Any]:
        """
        Search the web for recommendations.

        Args:
            context: Current context
            query: Search query
            category: Category for query refinement

        Returns:
            Web search results
        """
        self._logger.info("searching_web", query=query, category=category)

        # This would call brave.search MCP tool
        # Simulating results

        results = {
            "query": query,
            "category": category,
            "results": [
                {
                    "title": f"Result {i}",
                    "url": f"https://example.com/result{i}",
                    "snippet": f"Found {i} results for {query}",
                }
                for i in range(1, 6)
            ],
            "search_date": datetime.now().isoformat(),
        }

        self._logger.info("web_search_complete", results_count=len(results["results"]))

        return results

    # Helper methods

    def _generate_event_results(
        self,
        query: str,
        category: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Generate event search results."""
        events = [
            {
                "name": "Jazz Night at Blue Note",
                "date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
                "time": "20:00",
                "category": "music",
                "venue": "Blue Note Jazz Club",
                "price": 45,
                "description": "Local jazz trio performing classic standards",
                "url": "https://example.com/event1",
            },
            {
                "name": "Art Gallery Opening",
                "date": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
                "time": "18:00",
                "category": "art",
                "venue": "Modern Art Gallery",
                "price": 0,
                "description": "New contemporary art exhibition",
                "url": "https://example.com/event2",
            },
            {
                "name": "Food Festival",
                "date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
                "time": "11:00",
                "category": "food",
                "venue": "Central Park",
                "price": 20,
                "description": "Local food vendors and restaurants showcase",
                "url": "https://example.com/event3",
            },
            {
                "name": "Comedy Show",
                "date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "time": "19:30",
                "category": "entertainment",
                "venue": "Comedy Club",
                "price": 35,
                "description": "Stand-up comedy with local comedians",
                "url": "https://example.com/event4",
            },
        ]

        # Filter by category if specified
        if category != "all":
            events = [e for e in events if e["category"] == category]

        return events[:max_results]

    def _generate_restaurant_results(
        self,
        cuisine: Optional[str],
        price_range: str,
        party_size: int,
    ) -> List[Dict[str, Any]]:
        """Generate restaurant search results."""
        restaurants = [
            {
                "id": "rest_001",
                "name": "Italian Trattoria",
                "cuisine": "Italian",
                "price_range": "moderate",
                "rating": 4.7,
                "reviews": 345,
                "address": "123 Main St",
                "phone": "(555) 123-4567",
                "hours": "11am-11pm",
                "website": "https://example.com/rest1",
            },
            {
                "id": "rest_002",
                "name": "Sushi Master",
                "cuisine": "Japanese",
                "price_range": "upscale",
                "rating": 4.9,
                "reviews": 567,
                "address": "456 Park Ave",
                "phone": "(555) 234-5678",
                "hours": "5pm-midnight",
                "website": "https://example.com/rest2",
            },
            {
                "id": "rest_003",
                "name": "Burger Place",
                "cuisine": "American",
                "price_range": "budget",
                "rating": 4.3,
                "reviews": 234,
                "address": "789 Oak St",
                "phone": "(555) 345-6789",
                "hours": "11am-10pm",
                "website": "https://example.com/rest3",
            },
            {
                "id": "rest_004",
                "name": "Fine Dining Co.",
                "cuisine": "French",
                "price_range": "fine",
                "rating": 4.8,
                "reviews": 456,
                "address": "321 Elm St",
                "phone": "(555) 456-7890",
                "hours": "5pm-11pm",
                "website": "https://example.com/rest4",
            },
        ]

        # Filter by price range if specified
        if price_range != "all":
            restaurants = [
                r for r in restaurants
                if r["price_range"] == price_range
            ]

        # Filter by cuisine if specified
        if cuisine:
            restaurants = [
                r for r in restaurants
                if r["cuisine"].lower() == cuisine.lower()
            ]

        return restaurants

    def _generate_activity_results(
        self,
        category: str,
        duration_minutes: int,
    ) -> List[Dict[str, Any]]:
        """Generate activity discovery results."""
        activities = [
            {
                "name": "Rock Climbing",
                "category": "fitness",
                "duration_minutes": 90,
                "price": 25,
                "description": "Indoor rock climbing at Climb gym",
                "address": "123 Fitness St",
            },
            {
                "name": "Pottery Class",
                "category": "creative",
                "duration_minutes": 120,
                "price": 50,
                "description": "Learn pottery with local artist",
                "address": "456 Arts Ave",
            },
            {
                "name": "Hiking Trail",
                "category": "outdoor",
                "duration_minutes": 180,
                "price": 0,
                "description": "Scenic hiking trail with views",
                "address": "Mountain Park",
            },
            {
                "name": "Yoga Class",
                "category": "wellness",
                "duration_minutes": 60,
                "price": 20,
                "description": "Vinyasa yoga for all levels",
                "address": "789 Wellness St",
            },
            {
                "name": "Board Game Night",
                "category": "entertainment",
                "duration_minutes": 120,
                "price": 15,
                "description": "Play board games at the café",
                "address": "321 Game Café",
            },
        ]

        if category != "all":
            activities = [a for a in activities if a["category"] == category]

        return activities

    def _check_restaurant_availability(
        self,
        restaurant: Dict[str, Any],
        date: str,
        time: str,
        party_size: int,
    ) -> Dict[str, Any]:
        """Check if restaurant has availability."""
        # Simulate availability check
        import hashlib

        # Deterministic based on input
        hash_val = hashlib.md5(
            f"{restaurant.get('id')}{date}{time}{party_size}".encode()
        ).hexdigest()
        available = int(hash_val, 16) % 2 == 0

        return {
            "has_availability": available,
            "available_times": [
                time,
                "19:30",
                "20:00",
            ] if available else [],
        }

    def _is_within_date_range(
        self,
        date_str: str,
        start: str,
        end: str,
    ) -> bool:
        """Check if date is within range."""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            start_date = datetime.strptime(start, "%Y-%m-%d")
            end_date = datetime.strptime(end, "%Y-%m-%d")
            return start_date <= date <= end_date
        except (ValueError, TypeError):
            return False

    def _get_search_tips(self, category: str) -> List[str]:
        """Get search tips for category."""
        tips = {
            "music": [
                "Check venues' websites for seat availability",
                "Arrive early for popular shows",
                "Many venues have drink minimums",
            ],
            "art": [
                "Gallery openings often have free wine",
                "Photography allowed at most galleries",
                "Check opening hours before visiting",
            ],
            "food": [
                "Food festivals get crowded in afternoon",
                "Bring cash for food vendors",
                "Come hungry!",
            ],
        }
        return tips.get(category, ["Check availability in advance", "Read recent reviews"])

    def _get_restaurant_tips(self, price_range: str) -> List[str]:
        """Get restaurant tips for price range."""
        tips = {
            "budget": [
                "Often have lunch specials",
                "Arrive during off-peak hours",
                "Call ahead to avoid waits",
            ],
            "moderate": [
                "Good for casual dates",
                "Often accept walk-ins",
                "Check parking availability",
            ],
            "upscale": [
                "Reservations highly recommended",
                "Dress code may apply",
                "Great for special occasions",
            ],
            "fine": [
                "Book 2+ weeks in advance",
                "Dress formally",
                "Expect tasting menus",
            ],
        }
        return tips.get(price_range, ["Check reviews before going"])

    def _get_activity_tips(self, category: str) -> List[str]:
        """Get activity tips for category."""
        tips = {
            "fitness": [
                "Book classes in advance",
                "Bring water and towel",
                "Arrive 10 minutes early",
            ],
            "creative": [
                "Beginner-friendly classes available",
                "Materials provided",
                "Take home your creations",
            ],
            "outdoor": [
                "Check weather forecast",
                "Start early in the day",
                "Bring sun protection",
            ],
            "entertainment": [
                "Meet new people",
                "Great for social groups",
                "Often have snacks/drinks",
            ],
        }
        return tips.get(category, ["Check availability", "Book in advance if popular"])

    def _generate_rec_id(self) -> str:
        """Generate recommendation ID."""
        import uuid
        return f"rec_{uuid.uuid4().hex[:8]}"

    def _generate_booking_id(self) -> str:
        """Generate booking ID."""
        import uuid
        return uuid.uuid4().hex[:8]
