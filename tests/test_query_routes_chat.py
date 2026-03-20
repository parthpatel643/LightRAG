"""
Integration tests for the chat-enhanced /query routes.

Uses FastAPI's TestClient with a fully mocked LightRAG instance so no real
LLM or storage is needed.
"""

# Set sys.argv before any LightRAG imports so argparse doesn't choke on
# pytest's own command-line arguments.
import sys
sys.argv = ["test"]

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightrag.api.chat_session import SessionStore
from lightrag.api.routers.query_routes import create_query_routes


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_rag(llm_response_text: str = "Mocked LLM answer"):
    """Build a minimal mock LightRAG instance."""
    rag = MagicMock()
    rag.llm_model_func = AsyncMock(return_value=json.dumps({
        "intent": "rag_query", "response": None
    }))

    async def _aquery_llm(query, param=None):
        return {
            "llm_response": {"content": llm_response_text, "is_streaming": False},
            "data": {"references": [], "chunks": []},
        }

    rag.aquery_llm = _aquery_llm
    return rag


def _build_app(rag, store: SessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(create_query_routes(rag, api_key=None, top_k=10, store=store))
    return app


# ─────────────────────────────────────────────────────────────────────────────
# /query (non-streaming)
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryRouteSession:

    def setup_method(self):
        self.store = SessionStore()
        self.rag = _make_rag("Test answer")
        self.app = _build_app(self.rag, self.store)
        self.client = TestClient(self.app)

    def _post(self, payload: dict):
        return self.client.post("/query", json=payload)

    def test_new_session_created(self):
        resp = self._post({"query": "Hello", "mode": "mix"})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"] is not None

    def test_same_session_returned_when_provided(self):
        # First request creates a session
        r1 = self._post({"query": "First question", "mode": "mix"})
        sid = r1.json()["session_id"]

        # Second request with that session_id echoes it back
        r2 = self._post({"query": "Follow-up", "mode": "mix", "session_id": sid})
        assert r2.json()["session_id"] == sid

    def test_history_grows_between_turns(self):
        r1 = self._post({"query": "Turn 1", "mode": "mix"})
        sid = r1.json()["session_id"]

        r2 = self._post({"query": "Turn 2", "mode": "mix", "session_id": sid})
        assert r2.status_code == 200

        # Session should hold both exchanges now
        history = self.store.get_history(sid)
        assert len(history) == 4  # 2 user + 2 assistant msgs

    def test_response_content_returned(self):
        resp = self._post({"query": "What is AI?", "mode": "mix"})
        assert resp.json()["response"] == "Test answer"

    def test_intent_classification_disabled(self):
        """With enable_intent_classification=False the classifier is skipped."""
        resp = self._post({
            "query": "Hi there",
            "mode": "mix",
            "enable_intent_classification": False,
        })
        assert resp.status_code == 200
        assert resp.json()["response"] == "Test answer"

    def test_out_of_scope_returns_refusal(self):
        """OUT_OF_SCOPE intent → polite refusal, no RAG call."""
        self.rag.llm_model_func = AsyncMock(return_value=json.dumps({
            "intent": "out_of_scope",
            "response": "Sorry, that is outside my scope.",
        }))
        resp = self._post({"query": "Give me a cake recipe", "mode": "mix"})
        assert resp.status_code == 200
        assert "Sorry" in resp.json()["response"] or "outside" in resp.json()["response"].lower()
        # Out-of-scope should NOT be stored in session history
        sid = resp.json()["session_id"]
        history = self.store.get_history(sid)
        assert len(history) == 0

    def test_memory_recall_synthesises_answer(self):
        """MEMORY_RECALL intent → direct_response used, stored in session."""
        self.rag.llm_model_func = AsyncMock(return_value=json.dumps({
            "intent": "memory_recall",
            "response": "You previously asked about AI.",
        }))
        resp = self._post({"query": "What did I ask?", "mode": "mix"})
        assert resp.status_code == 200
        assert "AI" in resp.json()["response"]
        # Memory recall IS stored in session
        sid = resp.json()["session_id"]
        assert len(self.store.get_history(sid)) == 2

    def test_chit_chat_uses_rag_instance(self):
        """CHIT_CHAT → bypass mode forwarded to aquery_llm (no error)."""
        self.rag.llm_model_func = AsyncMock(return_value=json.dumps({
            "intent": "chit_chat",
            "response": None,
        }))
        resp = self._post({"query": "Hi, how are you?", "mode": "mix"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "Test answer"


# ─────────────────────────────────────────────────────────────────────────────
# /query/stream
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryStreamSession:

    def setup_method(self):
        self.store = SessionStore()

        rag = MagicMock()
        # Classifier always returns rag_query
        rag.llm_model_func = AsyncMock(return_value=json.dumps({
            "intent": "rag_query", "response": None
        }))

        async def _aquery_llm(query, param=None):
            return {
                "llm_response": {"content": "Streamed answer", "is_streaming": False},
                "data": {"references": [], "chunks": []},
            }

        rag.aquery_llm = _aquery_llm
        self.rag = rag
        self.app = _build_app(rag, self.store)
        self.client = TestClient(self.app)

    def _stream(self, payload: dict):
        return self.client.post("/query/stream", json=payload)

    def _parse_ndjson(self, content: bytes) -> list[dict]:
        lines = content.decode().strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_stream_returns_session_id(self):
        resp = self._stream({"query": "Hello", "mode": "mix", "stream": False})
        assert resp.status_code == 200
        chunks = self._parse_ndjson(resp.content)
        # session_id must appear in one of the chunks
        all_keys = {k for chunk in chunks for k in chunk}
        assert "session_id" in all_keys

    def test_stream_session_continuity(self):
        r1 = self._stream({"query": "Question 1", "mode": "mix", "stream": False})
        chunks1 = self._parse_ndjson(r1.content)
        sid = next(c["session_id"] for c in chunks1 if "session_id" in c)

        r2 = self._stream({
            "query": "Question 2",
            "mode": "mix",
            "stream": False,
            "session_id": sid,
        })
        chunks2 = self._parse_ndjson(r2.content)
        returned_sid = next(c["session_id"] for c in chunks2 if "session_id" in c)
        assert returned_sid == sid

        # Session should have both exchanges stored
        assert len(self.store.get_history(sid)) == 4

    def test_stream_out_of_scope_direct_response(self):
        self.rag.llm_model_func = AsyncMock(return_value=json.dumps({
            "intent": "out_of_scope",
            "response": "Sorry, out of scope.",
        }))
        resp = self._stream({"query": "cake recipe", "mode": "mix"})
        chunks = self._parse_ndjson(resp.content)
        combined = " ".join(c.get("response", "") for c in chunks)
        assert "sorry" in combined.lower() or "scope" in combined.lower()


# ─────────────────────────────────────────────────────────────────────────────
# /sessions/{session_id} endpoints (tested via the server module mock)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionEndpoints:
    """Test the GET/DELETE /sessions/{session_id} endpoints added in lightrag_server."""

    def setup_method(self):
        self.store = SessionStore()
        self.rag = _make_rag()

        # Build a minimal app that includes the session endpoints manually
        # (mirrors what lightrag_server does)
        from fastapi import HTTPException
        app = FastAPI()
        app.include_router(create_query_routes(self.rag, api_key=None, top_k=10, store=self.store))

        @app.get("/sessions/{session_id}")
        async def get_session(session_id: str):
            history = self.store.get_history(session_id)
            if not history and session_id not in self.store.list_sessions():
                raise HTTPException(status_code=404, detail="Not found")
            return {"session_id": session_id, "history": history}

        @app.delete("/sessions/{session_id}")
        async def delete_session(session_id: str):
            deleted = self.store.delete(session_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Not found")
            return {"session_id": session_id, "status": "deleted"}

        self.client = TestClient(app)

    def test_get_session_after_query(self):
        r = self.client.post("/query", json={"query": "Hello", "mode": "mix"})
        sid = r.json()["session_id"]

        r2 = self.client.get(f"/sessions/{sid}")
        assert r2.status_code == 200
        data = r2.json()
        assert data["session_id"] == sid
        assert len(data["history"]) == 2

    def test_get_nonexistent_session_returns_404(self):
        r = self.client.get("/sessions/does-not-exist")
        assert r.status_code == 404

    def test_delete_session(self):
        r = self.client.post("/query", json={"query": "Hello", "mode": "mix"})
        sid = r.json()["session_id"]

        rd = self.client.delete(f"/sessions/{sid}")
        assert rd.status_code == 200
        assert rd.json()["status"] == "deleted"

        # Session should be gone
        rg = self.client.get(f"/sessions/{sid}")
        assert rg.status_code == 404

    def test_delete_nonexistent_session_returns_404(self):
        r = self.client.delete("/sessions/does-not-exist")
        assert r.status_code == 404
