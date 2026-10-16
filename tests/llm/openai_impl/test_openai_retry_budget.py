"""Retry budget for gateway calls is configurable at call time.

A transient gateway outage that outlasts three quick attempts used to fail the
whole query ("No relevant context found") or embedding batch. The attempt
count stays 3 by default and can be raised with OPENAI_LLM_MAX_ATTEMPTS /
OPENAI_EMBEDDING_MAX_ATTEMPTS.
"""

import httpx
import pytest
from tenacity import RetryError, wait_none

from lightrag.llm.openai import openai_complete_if_cache, openai_embed

pytestmark = pytest.mark.offline

_COMPLETION = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "m",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}
_EMBEDDING = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
    "model": "m",
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
}


def _factory(failures: int, body: dict):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise httpx.ConnectError("gateway blip", request=request)
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    return (lambda: httpx.AsyncClient(transport=transport)), calls


async def _complete(factory):
    return await openai_complete_if_cache.retry_with(wait=wait_none())(
        model="m", prompt="p", api_key="k", base_url="http://gw/v1",
        openai_client_configs={"http_client": factory},
    )


async def _embed(factory):
    return await openai_embed.func.retry_with(wait=wait_none())(
        ["t"], model="m", api_key="k", base_url="http://gw/v1",
        client_configs={"http_client": factory},
    )


@pytest.mark.asyncio
async def test_completion_default_budget_is_three_attempts(monkeypatch):
    monkeypatch.delenv("OPENAI_LLM_MAX_ATTEMPTS", raising=False)
    factory, calls = _factory(3, _COMPLETION)
    with pytest.raises(RetryError):
        await _complete(factory)
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_completion_budget_follows_env(monkeypatch):
    monkeypatch.setenv("OPENAI_LLM_MAX_ATTEMPTS", "5")
    factory, calls = _factory(4, _COMPLETION)
    assert await _complete(factory) == "OK"
    assert calls["n"] == 5


@pytest.mark.asyncio
async def test_embedding_budget_follows_env(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MAX_ATTEMPTS", "5")
    factory, calls = _factory(4, _EMBEDDING)
    result = await _embed(factory)
    assert result.shape == (1, 2)
    assert calls["n"] == 5
