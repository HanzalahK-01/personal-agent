from __future__ import annotations
"""Memory store for personal AI agent system using PostgreSQL and pgvector."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Optional, Literal


import asyncpg
import structlog
from asyncpg import Pool, Connection

logger = structlog.get_logger(__name__)

# Type aliases for readability
CategoryType = Literal["fact", "preference", "event", "relationship", "routine", "shopping"]
RoleType = Literal["user", "assistant", "system"]
PlanStatusType = Literal["pending", "approved", "executing", "completed", "failed", "cancelled"]
PriorityType = Literal["need", "want"]
ShoppingStatusType = Literal["active", "purchased", "archived"]
EventType = Literal["date", "anniversary", "gift", "note"]


class MemoryStore:
    """Async PostgreSQL memory store with pgvector for semantic search."""

    def __init__(self, dsn: str, min_size: int = 2, max_size: int = 10):
        """
        Initialize MemoryStore with database connection parameters.

        Args:
            dsn: PostgreSQL connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        self.dsn = dsn
        self.pool: Optional[Pool] = None
        self.min_size = min_size
        self.max_size = max_size

    async def init(self) -> None:
        """Initialize connection pool and create schema if needed."""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=60,
            )
            logger.info("memory_store_initialized", pool_size=(self.min_size, self.max_size))

            # Run schema initialization
            async with self.pool.acquire() as conn:
                await self._ensure_schema(conn)

        except Exception as e:
            logger.error("memory_store_init_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("memory_store_closed")

    async def _ensure_schema(self, conn: Connection) -> None:
        """Create schema if it doesn't exist."""
        try:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgvector;")

            # Check if tables exist
            result = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'conversations'
                )
                """
            )

            if not result:
                # Read and execute schema file
                with open("memory/schema.sql", "r") as f:
                    schema = f.read()
                    # Execute schema in a transaction
                    await conn.execute(schema)
                logger.info("memory_schema_created")
            else:
                logger.debug("memory_schema_already_exists")

        except FileNotFoundError:
            logger.warning("schema_file_not_found", path="memory/schema.sql")
        except Exception as e:
            logger.error("schema_initialization_failed", error=str(e))
            raise

    async def save_conversation(
        self,
        user_id: int,
        agent: str,
        message: str,
        role: RoleType,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Save a conversation message.

        Args:
            user_id: User identifier
            agent: Agent name (e.g., 'scheduler', 'inbox')
            message: Message content
            role: Who sent the message (user/assistant/system)
            metadata: Additional context (tool_calls, function_name, etc.)
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversations (user_id, agent_name, message, role, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    user_id,
                    agent,
                    message,
                    role,
                    json.dumps(metadata) if metadata else None,
                )
            logger.debug(
                "conversation_saved",
                user_id=str(user_id),
                agent=agent,
                role=role,
            )
        except Exception as e:
            logger.error(
                "save_conversation_failed",
                user_id=str(user_id),
                agent=agent,
                error=str(e),
            )
            raise

    async def get_conversation_history(
        self,
        user_id: int,
        agent: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get conversation history for a user, optionally filtered by agent.

        Args:
            user_id: User identifier
            agent: Optional agent filter
            limit: Maximum conversations to return

        Returns:
            List of conversation dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                if agent:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, agent_name, message, role, metadata, created_at
                        FROM conversations
                        WHERE user_id = $1 AND agent_name = $2
                        ORDER BY created_at DESC
                        LIMIT $3
                        """,
                        user_id,
                        agent,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, agent_name, message, role, metadata, created_at
                        FROM conversations
                        WHERE user_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2
                        """,
                        user_id,
                        limit,
                    )

            return [self._row_to_dict(row) for row in reversed(rows)]

        except Exception as e:
            logger.error(
                "get_conversation_history_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def save_memory(
        self,
        user_id: int,
        category: CategoryType,
        key: str,
        value: str,
        source_agent: str,
        embedding: Optional[list[float]] = None,
        confidence: float = 1.0,
        expires_at: Optional[datetime] = None,
    ) -> int:
        """
        Save or update a memory.

        Args:
            user_id: User identifier
            category: Memory category
            key: Memory key/identifier
            value: Memory content
            source_agent: Which agent created this memory
            embedding: Optional vector embedding (1536 dims)
            confidence: Confidence score 0-1
            expires_at: Optional expiration datetime

        Returns:
            Memory ID
        """
        try:
            async with self.pool.acquire() as conn:
                memory_id = await conn.fetchval(
                    """
                    INSERT INTO memories
                    (user_id, category, key, value, embedding, confidence, source_agent, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (user_id, category, key)
                    DO UPDATE SET
                        value = $4,
                        embedding = $5,
                        confidence = $6,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    user_id,
                    category,
                    key,
                    value,
                    embedding,
                    confidence,
                    source_agent,
                    expires_at,
                )
            logger.debug(
                "memory_saved",
                user_id=str(user_id),
                category=category,
                key=key,
            )
            return memory_id

        except Exception as e:
            logger.error(
                "save_memory_failed",
                user_id=str(user_id),
                category=category,
                error=str(e),
            )
            raise

    async def get_memories(
        self,
        user_id: int,
        category: Optional[CategoryType] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Retrieve memories for a user, optionally filtered by category.

        Args:
            user_id: User identifier
            category: Optional category filter
            limit: Maximum memories to return

        Returns:
            List of memory dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                if category:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, category, key, value, confidence, source_agent, created_at, updated_at, expires_at
                        FROM memories
                        WHERE user_id = $1 AND category = $2
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                        ORDER BY updated_at DESC
                        LIMIT $3
                        """,
                        user_id,
                        category,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, category, key, value, confidence, source_agent, created_at, updated_at, expires_at
                        FROM memories
                        WHERE user_id = $1
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                        ORDER BY updated_at DESC
                        LIMIT $2
                        """,
                        user_id,
                        limit,
                    )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "get_memories_failed",
                user_id=str(user_id),
                category=category,
                error=str(e),
            )
            raise

    async def search_memories(
        self,
        user_id: int,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Semantic search memories using pgvector cosine similarity.

        Args:
            user_id: User identifier
            query_embedding: Query vector (1536 dims)
            top_k: Number of top results to return

        Returns:
            List of similar memory dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, user_id, category, key, value, confidence, source_agent,
                        created_at, updated_at, expires_at,
                        1 - (embedding <=> $2::vector) AS similarity
                    FROM memories
                    WHERE user_id = $1
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    AND embedding IS NOT NULL
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    user_id,
                    query_embedding,
                    top_k,
                )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "search_memories_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def save_plan(
        self,
        user_id: int,
        agent: str,
        steps: list[dict],
    ) -> int:
        """
        Create a new plan.

        Args:
            user_id: User identifier
            agent: Agent creating the plan
            steps: List of plan steps with action, status, etc.

        Returns:
            Plan ID
        """
        try:
            async with self.pool.acquire() as conn:
                plan_id = await conn.fetchval(
                    """
                    INSERT INTO plans (user_id, agent_name, plan_steps, status)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    user_id,
                    agent,
                    json.dumps(steps),
                    "pending",
                )
            logger.debug(
                "plan_saved",
                user_id=str(user_id),
                agent=agent,
                plan_id=plan_id,
            )
            return plan_id

        except Exception as e:
            logger.error(
                "save_plan_failed",
                user_id=str(user_id),
                agent=agent,
                error=str(e),
            )
            raise

    async def update_plan_status(
        self,
        plan_id: int,
        status: PlanStatusType,
    ) -> None:
        """
        Update plan status.

        Args:
            plan_id: Plan identifier
            status: New status
        """
        try:
            async with self.pool.acquire() as conn:
                # Set approved_at if transitioning to approved
                if status == "approved":
                    await conn.execute(
                        """
                        UPDATE plans
                        SET status = $1, updated_at = CURRENT_TIMESTAMP, approved_at = CURRENT_TIMESTAMP
                        WHERE id = $2
                        """,
                        status,
                        plan_id,
                    )
                # Set completed_at if transitioning to completed
                elif status == "completed":
                    await conn.execute(
                        """
                        UPDATE plans
                        SET status = $1, updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
                        WHERE id = $2
                        """,
                        status,
                        plan_id,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE plans
                        SET status = $1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = $2
                        """,
                        status,
                        plan_id,
                    )

            logger.debug("plan_status_updated", plan_id=plan_id, status=status)

        except Exception as e:
            logger.error(
                "update_plan_status_failed",
                plan_id=plan_id,
                status=status,
                error=str(e),
            )
            raise

    async def get_active_plans(self, user_id: int) -> list[dict]:
        """
        Get active plans for a user (pending/approved/executing).

        Args:
            user_id: User identifier

        Returns:
            List of active plan dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, agent_name, plan_steps, status, created_at, updated_at, approved_at, completed_at
                    FROM plans
                    WHERE user_id = $1 AND status IN ('pending', 'approved', 'executing')
                    ORDER BY created_at DESC
                    """,
                    user_id,
                )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "get_active_plans_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def upsert_routine(
        self,
        user_id: int,
        name: str,
        schedule: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Create or update a routine.

        Args:
            user_id: User identifier
            name: Routine name
            schedule: Cron-like schedule (e.g., "daily", "0 9 * * 1-5")
            metadata: Optional metadata (description, tags, etc.)

        Returns:
            Routine ID
        """
        try:
            async with self.pool.acquire() as conn:
                routine_id = await conn.fetchval(
                    """
                    INSERT INTO routines (user_id, name, schedule, metadata)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, name)
                    DO UPDATE SET schedule = $3, metadata = $4, updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    user_id,
                    name,
                    schedule,
                    json.dumps(metadata) if metadata else None,
                )

            logger.debug(
                "routine_upserted",
                user_id=str(user_id),
                routine_name=name,
                routine_id=routine_id,
            )
            return routine_id

        except Exception as e:
            logger.error(
                "upsert_routine_failed",
                user_id=str(user_id),
                routine_name=name,
                error=str(e),
            )
            raise

    async def complete_routine(
        self,
        user_id: int,
        routine_name: str,
    ) -> None:
        """
        Mark a routine as completed, updating streak.

        Args:
            user_id: User identifier
            routine_name: Name of the routine
        """
        try:
            async with self.pool.acquire() as conn:
                # Get current streak
                routine = await conn.fetchrow(
                    """
                    SELECT id, last_completed, streak
                    FROM routines
                    WHERE user_id = $1 AND name = $2
                    """,
                    user_id,
                    routine_name,
                )

                if not routine:
                    logger.warning(
                        "routine_not_found",
                        user_id=str(user_id),
                        routine_name=routine_name,
                    )
                    return

                # Calculate new streak (increment if completed today, reset otherwise)
                now = datetime.now()
                last_completed = routine["last_completed"]
                current_streak = routine["streak"]

                if last_completed and (now.date() - last_completed.date()).days == 1:
                    # Completed yesterday, continue streak
                    new_streak = current_streak + 1
                elif last_completed and (now.date() - last_completed.date()).days == 0:
                    # Already completed today, keep same streak
                    new_streak = current_streak
                else:
                    # Break in streak, reset to 1
                    new_streak = 1

                await conn.execute(
                    """
                    UPDATE routines
                    SET last_completed = CURRENT_TIMESTAMP,
                        streak = $3,
                        total_completions = total_completions + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $1 AND name = $2
                    """,
                    user_id,
                    routine_name,
                    new_streak,
                )

            logger.debug(
                "routine_completed",
                user_id=str(user_id),
                routine_name=routine_name,
            )

        except Exception as e:
            logger.error(
                "complete_routine_failed",
                user_id=str(user_id),
                routine_name=routine_name,
                error=str(e),
            )
            raise

    async def get_routines(self, user_id: int) -> list[dict]:
        """
        Get all routines for a user.

        Args:
            user_id: User identifier

        Returns:
            List of routine dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, name, schedule, last_completed, streak, total_completions, metadata, created_at, updated_at
                    FROM routines
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    """,
                    user_id,
                )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "get_routines_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def add_shopping_item(
        self,
        user_id: int,
        name: str,
        category: Optional[str] = None,
        priority: PriorityType = "want",
        price_target: Optional[float] = None,
        url: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Add item to shopping list.

        Args:
            user_id: User identifier
            name: Item name
            category: Item category
            priority: Priority (need/want)
            price_target: Target price
            url: Reference URL
            notes: Additional notes

        Returns:
            Shopping item ID
        """
        try:
            async with self.pool.acquire() as conn:
                item_id = await conn.fetchval(
                    """
                    INSERT INTO shopping_items
                    (user_id, name, category, priority, price_target, url, notes, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    user_id,
                    name,
                    category,
                    priority,
                    price_target,
                    url,
                    notes,
                    "active",
                )

            logger.debug(
                "shopping_item_added",
                user_id=str(user_id),
                item_name=name,
                item_id=item_id,
            )
            return item_id

        except Exception as e:
            logger.error(
                "add_shopping_item_failed",
                user_id=str(user_id),
                item_name=name,
                error=str(e),
            )
            raise

    async def get_shopping_list(
        self,
        user_id: int,
        status: ShoppingStatusType = "active",
    ) -> list[dict]:
        """
        Get shopping items for a user.

        Args:
            user_id: User identifier
            status: Filter by status (active/purchased/archived)

        Returns:
            List of shopping item dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, name, category, priority, price_target, url, notes, status, created_at, updated_at
                    FROM shopping_items
                    WHERE user_id = $1 AND status = $2
                    ORDER BY priority DESC, created_at DESC
                    """,
                    user_id,
                    status,
                )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "get_shopping_list_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def save_relationship_event(
        self,
        user_id: int,
        event_type: EventType,
        title: str,
        description: Optional[str] = None,
        date: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Save a relationship event.

        Args:
            user_id: User identifier
            event_type: Type of event (date/anniversary/gift/note)
            title: Event title
            description: Event description
            date: Event date/time
            metadata: Additional context (person_name, relationship, reminders, etc.)

        Returns:
            Event ID
        """
        try:
            async with self.pool.acquire() as conn:
                event_id = await conn.fetchval(
                    """
                    INSERT INTO relationship_events
                    (user_id, event_type, title, description, date, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    user_id,
                    event_type,
                    title,
                    description,
                    date,
                    json.dumps(metadata) if metadata else None,
                )

            logger.debug(
                "relationship_event_saved",
                user_id=str(user_id),
                event_type=event_type,
                event_id=event_id,
            )
            return event_id

        except Exception as e:
            logger.error(
                "save_relationship_event_failed",
                user_id=str(user_id),
                event_type=event_type,
                error=str(e),
            )
            raise

    async def get_relationship_events(
        self,
        user_id: int,
        event_type: Optional[EventType] = None,
    ) -> list[dict]:
        """
        Get relationship events for a user.

        Args:
            user_id: User identifier
            event_type: Optional filter by event type

        Returns:
            List of relationship event dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                if event_type:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, event_type, title, description, date, metadata, created_at, updated_at
                        FROM relationship_events
                        WHERE user_id = $1 AND event_type = $2
                        ORDER BY date DESC, created_at DESC
                        """,
                        user_id,
                        event_type,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, user_id, event_type, title, description, date, metadata, created_at, updated_at
                        FROM relationship_events
                        WHERE user_id = $1
                        ORDER BY date DESC, created_at DESC
                        """,
                        user_id,
                    )

            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "get_relationship_events_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def get_context_for_agent(
        self,
        user_id: int,
        agent_name: str,
        num_conversations: int = 10,
        num_memories: int = 20,
    ) -> dict[str, Any]:
        """
        Get contextual information for an agent (relevant memories + recent conversations).

        Args:
            user_id: User identifier
            agent_name: Agent requesting context
            num_conversations: Number of recent conversations to include
            num_memories: Number of relevant memories to include

        Returns:
            Dictionary with recent_conversations and memories
        """
        try:
            async with self.pool.acquire() as conn:
                # Get recent conversations for this agent
                conversations = await conn.fetch(
                    """
                    SELECT id, message, role, metadata, created_at
                    FROM conversations
                    WHERE user_id = $1 AND agent_name = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id,
                    agent_name,
                    num_conversations,
                )

                # Get recent memories (most updated ones)
                memories = await conn.fetch(
                    """
                    SELECT id, category, key, value, confidence, updated_at
                    FROM memories
                    WHERE user_id = $1
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    ORDER BY updated_at DESC
                    LIMIT $2
                    """,
                    user_id,
                    num_memories,
                )

            return {
                "recent_conversations": [self._row_to_dict(c) for c in reversed(conversations)],
                "memories": [self._row_to_dict(m) for m in memories],
            }

        except Exception as e:
            logger.error(
                "get_context_for_agent_failed",
                user_id=str(user_id),
                agent_name=agent_name,
                error=str(e),
            )
            raise

    @staticmethod
    def _row_to_dict(row: asyncpg.Record) -> dict:
        """Convert asyncpg Record to dictionary, handling special types."""
        if row is None:
            return {}

        result = dict(row)
        for key, value in result.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()

        return result
