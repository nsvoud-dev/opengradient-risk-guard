"""
OGChronosAgent: persistent AI agent with MemSync memory and x402 LLM.
Before answering, retrieves relevant context from memory; after each turn, reflects and saves facts.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .config import get_default_thread_id
from .errors import MemoryError, MemoryConfigError
from .memory import MemSyncClient
from .llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are OG Chronos, a helpful AI assistant with long-term memory. You have access to relevant facts about the user from past conversations. Use this context to personalize your responses. Be concise and natural. If the user shares new important information (preferences, name, job, interests, etc.), your response will be used to save those facts to memory."""

class OGChronosAgent:
    """
    Persistent agent: MemSync for long-term memory, OpenGradient x402 for LLM.
    Methods: retrieve_context, think, remember.
    """

    def __init__(
        self,
        llm=None,
        memory: MemSyncClient | None = None,
        thread_id: str | None = None,
        reflection_enabled: bool = True,
        memory_search_limit: int = 5,
    ):
        self._llm = llm or get_llm(use_langchain_llm=False)
        self._memory = memory or MemSyncClient()
        self._thread_id = thread_id or get_default_thread_id()
        self._reflection_enabled = reflection_enabled
        self._memory_search_limit = memory_search_limit
        self._conversation: List[dict] = []

    def retrieve_context(self, query: str) -> str:
        """
        Search MemSync for relevant past information about the user.
        Returns a single string (user_bio + relevant memories) for injection into context.
        """
        if self._memory is None:
            return ""
        try:
            result = self._memory.search(
                query=query,
                limit=self._memory_search_limit,
                rerank=True,
            )
        except MemoryConfigError:
            return ""
        except MemoryError as e:
            logger.warning("MemSync retrieve failed: %s", e)
            return ""

        parts = []
        user_bio = result.get("user_bio", "")
        if user_bio:
            parts.append(f"About the user: {user_bio}")
        memories = result.get("memories") or []
        for m in memories:
            fact = m.get("memory") if isinstance(m, dict) else str(m)
            if fact:
                parts.append(f"- {fact}")
        return "\n".join(parts) if parts else ""

    def think(
        self,
        user_message: str,
        include_memory_context: bool = True,
    ) -> str:
        """
        Produce an assistant reply: optionally pull context from MemSync, then run LLM.
        """
        context = ""
        if include_memory_context:
            context = self.retrieve_context(user_message)

        messages = []
        system_content = SYSTEM_PROMPT
        if context:
            system_content += f"\n\nRelevant context from memory:\n{context}"
        messages.append({"role": "system", "content": system_content})

        for msg in self._conversation[-20:]:  # recent in-session history
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        reply = self._llm.invoke(messages)

        self._conversation.append({"role": "user", "content": user_message})
        self._conversation.append({"role": "assistant", "content": reply})

        if self._reflection_enabled:
            self.remember(user_message, reply)

        return reply

    def remember(self, user_message: str, assistant_message: str) -> None:
        """
        Reflect on the exchange and save new important facts to MemSync.
        Stores the conversation so MemSync can extract and index memories.
        """
        if self._memory is None:
            return
        try:
            self._memory.store_messages(
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_message},
                ],
                thread_id=self._thread_id,
                source="chat",
            )
        except (MemoryError, MemoryConfigError) as e:
            logger.warning("MemSync remember (store) failed: %s", e)

    def set_thread_id(self, thread_id: str) -> None:
        self._thread_id = thread_id

    def clear_session(self) -> None:
        """Clear in-memory conversation only (MemSync is persistent)."""
        self._conversation.clear()
