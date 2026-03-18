from __future__ import annotations
"""
ShoppingAgent - Manages shopping lists and purchasing decisions.

Responsibilities:
- Maintain want/need lists
- Track items and prioritize
- Search for items and compare prices
- Suggest optimal buying times
- Monitor budgets and spending
"""

import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAgent

logger = structlog.get_logger()


class ShoppingAgent(BaseAgent):
    """Agent specialized in smart shopping and budgeting."""

    def __init__(self):
        """Initialize the ShoppingAgent."""
        super().__init__(
            name="ShoppingAgent",
            description="Manages shopping lists, tracks items, and suggests optimal timing",
            capabilities=[
                "tavily.search — search for products, prices, reviews, or where to buy something",
                "tavily.search_news — search for deals, sales, or product news",
                "todoist.add_task — add an item to the shopping list as a Todoist task with priority and due date",
                "todoist.get_tasks — retrieve existing shopping list tasks",
                "todoist.complete_task — mark a purchased item as done",
            ],
        )

        # Categories for organization
        self.categories = {
            "groceries": {"emoji": "🍎", "priority_weight": 1.5},
            "electronics": {"emoji": "🖥️", "priority_weight": 2.0},
            "clothing": {"emoji": "👕", "priority_weight": 1.0},
            "home": {"emoji": "🏠", "priority_weight": 1.3},
            "fitness": {"emoji": "💪", "priority_weight": 0.8},
            "entertainment": {"emoji": "🎮", "priority_weight": 0.5},
            "other": {"emoji": "📦", "priority_weight": 1.0},
        }

    @property
    def system_prompt(self) -> str:
        """System prompt for shopping and budgeting decisions."""
        return """You are a smart shopping assistant for Hanzalah, a 24-year-old data engineer.

Your role is to:
1. Help organize shopping priorities (need vs want)
2. Find best deals without analysis paralysis
3. Suggest optimal buying times
4. Prevent impulse purchases
5. Track spending and budgets

PERSONALITY:
- Practical and budget-conscious
- Understand difference between need and want
- Help delay gratification on non-essentials
- Celebrate smart purchases
- Data-driven price suggestions

SHOPPING PRINCIPLES:
- Needs (groceries, essentials): Buy when needed or on sale
- Wants (electronics, entertainment): Wait for sales events
- Electronics: Usually drop in price 2-4 weeks before new model launch
- Clothing: Best deals end-of-season
- Groceries: Weekly sales cycles
- 24-hour rule: Wait 24h before impulse purchases

BUDGET GUIDANCE:
- Track spending by category
- Alert if spending spike detected
- Suggest alternatives if budget exceeded
- Celebrate savings achievements
"""

    async def get_lists(
        self,
        context: Dict[str, Any],
        list_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get shopping lists (need vs want).

        Args:
            context: Current context
            list_type: 'need', 'want', or None for both

        Returns:
            Organized shopping lists
        """
        self._logger.info("fetching_lists", type=list_type)

        lists = context.get("shopping_lists", {
            "need": [],
            "want": [],
        })

        if list_type and list_type in lists:
            result = {list_type: lists[list_type]}
        else:
            result = lists

        # Enrich with stats
        for key in result:
            items = result[key]
            total_cost = sum(
                float(item.get("estimated_price", 0))
                for item in items
            )

            result[key] = {
                "items": self._sort_items_by_priority(items),
                "count": len(items),
                "total_estimated": total_cost,
                "categories_breakdown": self._categorize_items(items),
            }

        self._logger.info("lists_fetched", lists_count=len(result))

        return result

    async def add_item(
        self,
        context: Dict[str, Any],
        name: str,
        list_type: str = "want",
        category: str = "other",
        estimated_price: float = 0.0,
        priority: str = "medium",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Add item to shopping list.

        Args:
            context: Current context
            name: Item name
            list_type: 'need' or 'want'
            category: Item category
            estimated_price: Estimated price
            priority: Priority level
            notes: Optional notes

        Returns:
            Added item details
        """
        self._logger.info(
            "adding_item",
            name=name,
            list_type=list_type,
            priority=priority,
        )

        item = {
            "id": self._generate_item_id(),
            "name": name,
            "category": category,
            "estimated_price": estimated_price,
            "priority": priority,
            "added_date": datetime.now().isoformat(),
            "notes": notes,
            "status": "pending",
        }

        # For wants, suggest waiting period
        if list_type == "want":
            item["wait_until"] = (
                datetime.now().strftime("%Y-%m-%d")
            )
            item["reason"] = f"Added to {list_type} list - review in 24 hours"

        return {
            "added": True,
            "item": item,
            "message": self._get_add_message(list_type, priority),
        }

    async def remove_item(
        self,
        context: Dict[str, Any],
        item_id: str,
        reason: str = "completed",
    ) -> Dict[str, Any]:
        """
        Remove item from shopping list.

        Args:
            context: Current context
            item_id: ID of item to remove
            reason: Why item is being removed

        Returns:
            Removal confirmation
        """
        self._logger.info("removing_item", item_id=item_id, reason=reason)

        # Find and remove the item
        lists = context.get("shopping_lists", {})
        removed = None

        for list_type in ["need", "want"]:
            items = lists.get(list_type, [])
            for item in items:
                if item.get("id") == item_id:
                    removed = item
                    items.remove(item)
                    break

        if not removed:
            return {"removed": False, "error": f"Item {item_id} not found"}

        self._logger.info("item_removed", item=removed.get("name"))

        return {
            "removed": True,
            "item": removed,
            "reason": reason,
            "message": f"✓ Removed {removed.get('name')} from list",
        }

    async def search_item(
        self,
        context: Dict[str, Any],
        query: str,
        include_price_estimates: bool = True,
    ) -> Dict[str, Any]:
        """
        Search for item to get information and pricing.

        Args:
            context: Current context
            query: Item to search for
            include_price_estimates: Whether to estimate prices

        Returns:
            Item info, price ranges, and recommendations
        """
        self._logger.info("searching_item", query=query)

        # Simulate search results based on category
        category = self._guess_category(query)

        results = {
            "query": query,
            "category": category,
            "results": [
                {
                    "name": f"{query} - Brand A",
                    "price": self._estimate_base_price(query) * 0.9,
                    "rating": 4.5,
                    "reviews": 234,
                    "in_stock": True,
                },
                {
                    "name": f"{query} - Brand B",
                    "price": self._estimate_base_price(query),
                    "rating": 4.7,
                    "reviews": 589,
                    "in_stock": True,
                },
                {
                    "name": f"{query} - Premium",
                    "price": self._estimate_base_price(query) * 1.3,
                    "rating": 4.8,
                    "reviews": 156,
                    "in_stock": True,
                },
            ],
            "price_range": {
                "low": self._estimate_base_price(query) * 0.8,
                "avg": self._estimate_base_price(query),
                "high": self._estimate_base_price(query) * 1.5,
            },
            "timing_advice": self._get_timing_advice(category),
        }

        self._logger.info("search_completed", results_count=len(results["results"]))

        return results

    async def compare_prices(
        self,
        context: Dict[str, Any],
        item_name: str,
        retailers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Compare prices across retailers.

        Args:
            context: Current context
            item_name: Item to compare
            retailers: List of retailers to check

        Returns:
            Price comparison with best deals
        """
        retailers = retailers or ["Amazon", "Best Buy", "Walmart", "Target"]

        self._logger.info(
            "comparing_prices",
            item=item_name,
            retailers=len(retailers),
        )

        base_price = self._estimate_base_price(item_name)
        comparison = {}

        for retailer in retailers:
            # Simulate price variations
            import random
            price = base_price * (0.85 + random.uniform(0, 0.3))
            has_sale = random.random() > 0.6
            discount = random.uniform(5, 25) if has_sale else 0

            comparison[retailer] = {
                "price": round(price, 2),
                "on_sale": has_sale,
                "discount_percent": round(discount, 1) if has_sale else 0,
                "final_price": round(price * (1 - discount / 100), 2) if has_sale else round(price, 2),
                "shipping": "Free" if price > 35 else "$5.99",
                "in_stock": random.random() > 0.2,
            }

        # Find best deal
        best_deal = min(
            comparison.items(),
            key=lambda x: x[1]["final_price"]
        )

        self._logger.info(
            "price_comparison_complete",
            best_retailer=best_deal[0],
            best_price=best_deal[1]["final_price"],
        )

        return {
            "item": item_name,
            "comparison": comparison,
            "best_deal": {
                "retailer": best_deal[0],
                "final_price": best_deal[1]["final_price"],
                "savings": round(
                    max(c["final_price"] for c in comparison.values())
                    - best_deal[1]["final_price"],
                    2
                ),
            },
            "recommendation": f"Buy from {best_deal[0]} - best price at ${best_deal[1]['final_price']}",
        }

    async def suggest_timing(
        self,
        context: Dict[str, Any],
        item_name: str,
        category: str = "other",
    ) -> Dict[str, Any]:
        """
        Suggest when to buy an item.

        Args:
            context: Current context
            item_name: Item to purchase
            category: Item category

        Returns:
            Timing recommendation with reasoning
        """
        self._logger.info("suggesting_timing", item=item_name, category=category)

        timing = self._get_optimal_timing(category)

        return {
            "item": item_name,
            "category": category,
            "current_price": self._estimate_base_price(item_name),
            "optimal_timing": timing["timing"],
            "expected_discount": timing["expected_discount"],
            "reason": timing["reason"],
            "wait_recommendation": timing["wait"],
            "seasonal_context": timing.get("seasonal", "No seasonal factors"),
        }

    async def track_spending(
        self,
        context: Dict[str, Any],
        period: str = "month",
    ) -> Dict[str, Any]:
        """
        Track spending by category.

        Args:
            context: Current context
            period: 'week', 'month', or 'quarter'

        Returns:
            Spending breakdown and analysis
        """
        self._logger.info("tracking_spending", period=period)

        purchases = context.get("purchases", [])

        # Filter by period
        if period == "month":
            days = 30
        elif period == "quarter":
            days = 90
        else:
            days = 7

        recent_purchases = [
            p for p in purchases
            if self._is_within_days(p.get("date"), days)
        ]

        # Categorize spending
        spending_by_category = {}
        for purchase in recent_purchases:
            category = purchase.get("category", "other")
            amount = float(purchase.get("amount", 0))

            if category not in spending_by_category:
                spending_by_category[category] = 0

            spending_by_category[category] += amount

        total = sum(spending_by_category.values())

        # Calculate trends
        trends = {}
        for category, amount in spending_by_category.items():
            percent = (amount / total * 100) if total > 0 else 0
            trends[category] = {
                "amount": round(amount, 2),
                "percent": f"{percent:.1f}%",
            }

        self._logger.info(
            "spending_tracked",
            period=period,
            total=total,
            categories=len(trends),
        )

        return {
            "period": period,
            "total_spent": round(total, 2),
            "spending_by_category": trends,
            "top_category": max(trends.items(), key=lambda x: x[1]["amount"])[0] if trends else None,
            "insight": self._generate_spending_insight(spending_by_category, total),
        }

    # Helper methods

    def _sort_items_by_priority(self, items: List[Dict]) -> List[Dict]:
        """Sort items by priority and price."""
        priority_order = {"high": 0, "medium": 1, "low": 2}

        return sorted(
            items,
            key=lambda i: (
                priority_order.get(i.get("priority", "low"), 3),
                -float(i.get("estimated_price", 0)),
            )
        )

    def _categorize_items(self, items: List[Dict]) -> Dict[str, int]:
        """Count items by category."""
        breakdown = {}
        for item in items:
            category = item.get("category", "other")
            breakdown[category] = breakdown.get(category, 0) + 1
        return breakdown

    def _guess_category(self, query: str) -> str:
        """Guess category from query text."""
        query_lower = query.lower()

        category_keywords = {
            "groceries": ["food", "fruit", "vegetable", "milk", "bread"],
            "electronics": ["phone", "laptop", "computer", "tablet", "headphones"],
            "clothing": ["shirt", "pants", "shoes", "jacket", "dress"],
            "home": ["furniture", "lamp", "towel", "bedding", "kitchen"],
            "fitness": ["gym", "dumbbell", "yoga", "exercise", "running"],
            "entertainment": ["game", "movie", "book", "music"],
        }

        for category, keywords in category_keywords.items():
            if any(kw in query_lower for kw in keywords):
                return category

        return "other"

    def _estimate_base_price(self, item_name: str) -> float:
        """Estimate base price for item."""
        import hashlib

        # Create deterministic but varied prices
        hash_val = int(hashlib.md5(item_name.encode()).hexdigest(), 16)
        base_prices = {
            "groceries": hash_val % 50 + 5,
            "electronics": hash_val % 1000 + 100,
            "clothing": hash_val % 200 + 20,
            "home": hash_val % 300 + 30,
            "fitness": hash_val % 300 + 20,
        }

        category = self._guess_category(item_name)
        return float(base_prices.get(category, 50))

    def _get_timing_advice(self, category: str) -> str:
        """Get timing advice for a category."""
        timing_advice = {
            "groceries": "Buy weekly when on sale",
            "electronics": "Wait for seasonal sales (Black Friday, new model launches)",
            "clothing": "Buy end-of-season for best deals",
            "home": "Monitor for weekend sales and clearance",
            "fitness": "New Year and summer sales best",
            "entertainment": "Check for promotions before release",
        }

        return timing_advice.get(category, "Monitor for sales")

    def _get_optimal_timing(self, category: str) -> Dict[str, Any]:
        """Get optimal buying time for category."""
        timing_map = {
            "groceries": {
                "timing": "Weekly (Tuesdays/Wednesdays)",
                "expected_discount": "10-20%",
                "reason": "Weekly sales rotation",
                "wait": False,
                "seasonal": "Stock up before holidays",
            },
            "electronics": {
                "timing": "Black Friday, holiday season, new model launches",
                "expected_discount": "20-40%",
                "reason": "Retailers discount old models for new stock",
                "wait": True,
                "seasonal": "Best deals Nov-Dec and July-Aug",
            },
            "clothing": {
                "timing": "End of season (Jan for winter, July for summer)",
                "expected_discount": "30-70%",
                "reason": "Clearance sales for seasonal items",
                "wait": True,
                "seasonal": "Out-of-season sales are best",
            },
            "home": {
                "timing": "Weekend sales, holiday weekends",
                "expected_discount": "15-25%",
                "reason": "Regular promotional events",
                "wait": False,
                "seasonal": "Spring and fall sales common",
            },
            "fitness": {
                "timing": "January (New Year), May-June (summer prep)",
                "expected_discount": "20-30%",
                "reason": "Seasonal demand",
                "wait": True,
                "seasonal": "Peak seasons have best selection",
            },
            "entertainment": {
                "timing": "Birthday sales, holiday events",
                "expected_discount": "10-20%",
                "reason": "Occasional promotional events",
                "wait": False,
            },
        }

        return timing_map.get(
            category,
            {
                "timing": "Anytime",
                "expected_discount": "0-10%",
                "reason": "No specific seasonal pattern",
                "wait": False,
            }
        )

    def _is_within_days(self, date_str: str, days: int) -> bool:
        """Check if date is within N days."""
        try:
            from datetime import timedelta
            date = datetime.fromisoformat(date_str)
            cutoff = datetime.now() - timedelta(days=days)
            return date >= cutoff
        except (ValueError, TypeError):
            return False

    def _generate_spending_insight(
        self,
        spending_by_category: Dict[str, float],
        total: float,
    ) -> str:
        """Generate insight about spending patterns."""
        if not spending_by_category:
            return "No recent purchases to analyze."

        top_category = max(
            spending_by_category.items(),
            key=lambda x: x[1]
        )[0]
        top_amount = spending_by_category[top_category]
        percent = (top_amount / total * 100) if total > 0 else 0

        return f"{percent:.0f}% of spending in {top_category}. Review if aligned with goals."

    def _get_add_message(self, list_type: str, priority: str) -> str:
        """Get message when adding item."""
        if list_type == "want":
            return "✓ Added to wants list. Review in 24 hours before purchasing!"
        elif priority == "high":
            return "✓ Added to needs list. Mark as urgent!"
        else:
            return "✓ Added to needs list."

    def _generate_item_id(self) -> str:
        """Generate unique item ID."""
        import uuid
        return f"item_{uuid.uuid4().hex[:8]}"
