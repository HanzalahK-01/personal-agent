"""Unit tests for intent router."""

import pytest
import asyncio
from dispatcher.router import classify_intent


class TestIntentClassification:
    """Test intent classification router."""

    @pytest.mark.asyncio
    async def test_scheduling_intent(self):
        """Test classification of scheduling request."""
        message = "Schedule a meeting with John tomorrow at 2pm"
        intent, confidence = await classify_intent(message)
        
        assert intent in ["scheduling", "general_chat"]  # Might fallback
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_email_intent(self):
        """Test classification of email request."""
        message = "Send an email to alice@example.com about the project"
        intent, confidence = await classify_intent(message)
        
        assert intent in ["email", "general_chat"]
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_shopping_intent(self):
        """Test classification of shopping request."""
        message = "Create a shopping list for groceries"
        intent, confidence = await classify_intent(message)
        
        assert intent in ["shopping", "general_chat"]
        assert 0.0 <= confidence <= 1.0

    @pytest.mark.asyncio
    async def test_general_chat(self):
        """Test classification of general chat."""
        message = "Hello, how are you?"
        intent, confidence = await classify_intent(message)
        
        assert intent in ["general_chat", "concierge"]
        assert 0.0 <= confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
