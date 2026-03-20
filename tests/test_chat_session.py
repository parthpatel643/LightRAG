"""Unit tests for lightrag.api.chat_session and lightrag.api.chat_intent."""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from lightrag.api.chat_session import SessionStore, SessionData


# ─────────────────────────────────────────────────────────────────────────────
# SessionStore
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionStore:

    def test_get_or_create_new(self):
        store = SessionStore()
        sid, history = store.get_or_create(None)
        assert isinstance(sid, str) and len(sid) > 0
        assert history == []

    def test_get_or_create_explicit_id(self):
        store = SessionStore()
        sid, history = store.get_or_create("my-id")
        assert sid == "my-id"
        assert history == []

    def test_get_or_create_returns_existing(self):
        store = SessionStore()
        sid, _ = store.get_or_create(None)
        store.append(sid, "hello", "hi there")
        sid2, history = store.get_or_create(sid)
        assert sid2 == sid
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

    def test_append_and_get_history(self):
        store = SessionStore()
        sid, _ = store.get_or_create(None)
        store.append(sid, "q1", "a1")
        store.append(sid, "q2", "a2")
        h = store.get_history(sid)
        assert len(h) == 4
        assert h[0]["role"] == "user"
        assert h[0]["content"] == "q1"
        assert h[1]["role"] == "assistant"
        assert h[1]["content"] == "a1"

    def test_max_history_trimming(self):
        store = SessionStore(max_history=2)
        sid, _ = store.get_or_create(None)
        for i in range(5):
            store.append(sid, f"q{i}", f"a{i}")
        h = store.get_history(sid)
        # max_history=2 means 4 messages max
        assert len(h) == 4
        # Should be the last 2 pairs
        assert h[0]["content"] == "q3"
        assert h[2]["content"] == "q4"

    def test_delete_existing(self):
        store = SessionStore()
        sid, _ = store.get_or_create(None)
        assert store.delete(sid) is True
        assert store.get_history(sid) == []

    def test_delete_nonexistent(self):
        store = SessionStore()
        assert store.delete("does-not-exist") is False

    def test_list_sessions(self):
        store = SessionStore()
        sid1, _ = store.get_or_create(None)
        sid2, _ = store.get_or_create(None)
        ids = store.list_sessions()
        assert sid1 in ids and sid2 in ids

    def test_ttl_eviction(self):
        store = SessionStore(ttl_seconds=1)
        sid, _ = store.get_or_create(None)
        store.append(sid, "q", "a")

        # Manually backdate last_accessed to trigger eviction
        store._sessions[sid].last_accessed = time.time() - 2

        # Any access should trigger eviction
        ids = store.list_sessions()
        assert sid not in ids
        assert store.get_history(sid) == []

    def test_get_or_create_evicts_expired(self):
        store = SessionStore(ttl_seconds=1)
        sid, _ = store.get_or_create(None)
        store._sessions[sid].last_accessed = time.time() - 2

        # Creating a new session should evict the expired one
        new_sid, history = store.get_or_create(None)
        assert new_sid != sid
        assert sid not in store._sessions

    def test_history_isolation(self):
        """Two sessions should not share history."""
        store = SessionStore()
        sid1, _ = store.get_or_create(None)
        sid2, _ = store.get_or_create(None)
        store.append(sid1, "user q for 1", "assistant a for 1")
        assert store.get_history(sid2) == []

    def test_append_creates_session_if_missing(self):
        """append() should create the session if it doesn't exist yet."""
        store = SessionStore()
        store.append("brand-new-id", "q", "a")
        h = store.get_history("brand-new-id")
        assert len(h) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Intent classifier
# ─────────────────────────────────────────────────────────────────────────────

from lightrag.api.chat_intent import (
    Intent,
    IntentResult,
    classify_intent,
    _format_last_turns,
    _parse_llm_json,
)


class TestHelpers:

    def test_format_last_turns_empty(self):
        result = _format_last_turns([])
        assert "no conversation" in result.lower()

    def test_format_last_turns_trims_to_n(self):
        history = []
        for i in range(5):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})
        result = _format_last_turns(history, n_turns=2)
        lines = result.strip().splitlines()
        assert len(lines) == 4  # 2 turns × 2 messages

    def test_parse_llm_json_clean(self):
        raw = '{"intent": "rag_query", "response": null}'
        parsed = _parse_llm_json(raw)
        assert parsed["intent"] == "rag_query"

    def test_parse_llm_json_with_fence(self):
        raw = '```json\n{"intent": "chit_chat", "response": "Hey!"}\n```'
        parsed = _parse_llm_json(raw)
        assert parsed["intent"] == "chit_chat"
        assert parsed["response"] == "Hey!"


class TestClassifyIntent:

    def _make_rag(self, json_response: str):
        rag = MagicMock()
        rag.llm_model_func = AsyncMock(return_value=json_response)
        return rag

    def test_rag_query(self):
        rag = self._make_rag('{"intent": "rag_query", "response": null}')
        result = asyncio.run(
            classify_intent("What is the capital of France?", [], rag)
        )
        assert result.intent == Intent.RAG_QUERY
        assert result.direct_response is None

    def test_chit_chat(self):
        rag = self._make_rag('{"intent": "chit_chat", "response": null}')
        result = asyncio.run(
            classify_intent("Hi, how are you?", [], rag)
        )
        assert result.intent == Intent.CHIT_CHAT

    def test_memory_recall(self):
        rag = self._make_rag(
            '{"intent": "memory_recall", "response": "You asked about the capital of France."}'
        )
        result = asyncio.run(
            classify_intent("What did I ask earlier?", [], rag)
        )
        assert result.intent == Intent.MEMORY_RECALL
        assert "France" in result.direct_response

    def test_out_of_scope(self):
        rag = self._make_rag(
            '{"intent": "out_of_scope", "response": "Sorry, that is outside my scope."}'
        )
        result = asyncio.run(
            classify_intent("What is the recipe for chocolate cake?", [], rag)
        )
        assert result.intent == Intent.OUT_OF_SCOPE
        assert result.direct_response is not None

    def test_fallback_on_invalid_json(self):
        """Should fall back to RAG_QUERY when LLM returns garbage."""
        rag = self._make_rag("I cannot classify this right now.")
        result = asyncio.run(
            classify_intent("some query", [], rag)
        )
        assert result.intent == Intent.RAG_QUERY

    def test_fallback_on_unknown_intent(self):
        """Should fall back to RAG_QUERY when intent value is unrecognised."""
        rag = self._make_rag('{"intent": "unknown_intent_xyz", "response": null}')
        result = asyncio.run(
            classify_intent("some query", [], rag)
        )
        assert result.intent == Intent.RAG_QUERY

    def test_fallback_on_llm_exception(self):
        """Should fall back to RAG_QUERY when LLM call raises."""
        rag = MagicMock()
        rag.llm_model_func = AsyncMock(side_effect=RuntimeError("LLM down"))
        result = asyncio.run(
            classify_intent("some query", [], rag)
        )
        assert result.intent == Intent.RAG_QUERY

    def test_markdown_fence_stripped(self):
        """Handles LLM responses wrapped in ```json ... ``` fences."""
        rag = self._make_rag(
            '```json\n{"intent": "chit_chat", "response": null}\n```'
        )
        result = asyncio.run(
            classify_intent("Hello!", [], rag)
        )
        assert result.intent == Intent.CHIT_CHAT
