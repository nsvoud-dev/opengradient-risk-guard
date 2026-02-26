"""
MemSync long-term memory layer.
Stores and retrieves user preferences and dialogue history via MemSync REST API
(built on OpenGradient's verifiable inference and embeddings).
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .config import get_agent_id, get_default_thread_id, get_memsync_api_key
from .errors import MemoryError, MemoryConfigError

logger = logging.getLogger(__name__)

MEMSYNC_BASE = "https://api.memchat.io/v1"


class MemSyncClient:
    """Client for MemSync REST API: store conversations and semantic search."""

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str | None = None,
        default_thread_id: str | None = None,
    ):
        self.api_key = api_key or get_memsync_api_key()
        self.agent_id = agent_id or get_agent_id()
        self.default_thread_id = default_thread_id or get_default_thread_id()
        self._session = requests.Session()
        if self.api_key:
            self._session.headers["X-API-Key"] = self.api_key
            self._session.headers["Content-Type"] = "application/json"

    def _ensure_api_key(self) -> None:
        if not self.api_key:
            raise MemoryConfigError(
                "MEMSYNC_API_KEY is not set. Set it in .env or pass api_key to MemSyncClient."
            )

    def store_messages(
        self,
        messages: list[dict[str, str]],
        thread_id: str | None = None,
        source: str = "chat",
    ) -> dict[str, Any]:
        """Store a conversation; MemSync will extract and index memories."""
        self._ensure_api_key()
        url = f"{MEMSYNC_BASE}/memories"
        payload = {
            "messages": messages,
            "agent_id": self.agent_id,
            "thread_id": thread_id or self.default_thread_id,
            "source": source,
        }
        try:
            r = self._session.post(url, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise MemoryConfigError("MemSync API key invalid or missing.") from e
            if e.response.status_code == 429:
                raise MemoryError("MemSync rate limit exceeded; retry later.") from e
            raise MemoryError(f"MemSync store failed: {e}") from e
        except requests.exceptions.RequestException as e:
            raise MemoryError(f"MemSync network error: {e}") from e

    def search(
        self,
        query: str,
        limit: int = 5,
        rerank: bool = True,
    ) -> dict[str, Any]:
        """Semantic search over stored memories. Returns user_bio and memories."""
        self._ensure_api_key()
        url = f"{MEMSYNC_BASE}/memories/search"
        payload = {"query": query, "limit": limit, "rerank": rerank}
        try:
            r = self._session.post(url, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise MemoryConfigError("MemSync API key invalid or missing.") from e
            if e.response.status_code == 429:
                raise MemoryError("MemSync rate limit exceeded; retry later.") from e
            raise MemoryError(f"MemSync search failed: {e}") from e
        except requests.exceptions.RequestException as e:
            raise MemoryError(f"MemSync network error: {e}") from e
