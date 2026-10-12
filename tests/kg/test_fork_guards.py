"""Small guards: rerank TLS, bounded graph fan-out, Neptune mirror queue, Gremlin escaping."""

from __future__ import annotations

import asyncio

import pytest

from lightrag.base import BaseGraphStorage, _bounded_gather
from lightrag.utils import apply_rerank_if_enabled

pytestmark = pytest.mark.offline


@pytest.mark.asyncio
async def test_rerank_call_does_not_force_ssl_verification_off():
    seen = {}

    async def rerank_func(**kwargs):
        seen.update(kwargs)
        return [{"index": 0, "relevance_score": 0.9}]

    await apply_rerank_if_enabled(
        query="q",
        retrieved_docs=[{"content": "a"}],
        global_config={"rerank_model_func": rerank_func},
        top_n=1,
    )
    assert "verify_ssl" not in seen


@pytest.mark.asyncio
async def test_rerank_without_top_n_is_not_a_type_error():
    async def rerank_func(**kwargs):
        assert kwargs["top_n"] is None
        return [{"index": 0, "relevance_score": 0.5}]

    out = await apply_rerank_if_enabled(
        query="q",
        retrieved_docs=[{"content": "a"}],
        global_config={"rerank_model_func": rerank_func},
    )
    assert out[0]["rerank_score"] == 0.5


@pytest.mark.asyncio
async def test_bounded_gather_caps_concurrency_and_keeps_order(monkeypatch):
    monkeypatch.setenv("GRAPH_BATCH_CONCURRENCY", "3")
    in_flight = peak = 0

    async def work(value):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight -= 1
        return value

    results = await _bounded_gather([work(i) for i in range(20)])
    assert results == list(range(20))
    assert peak <= 3


def test_default_graph_batches_use_the_bounded_helper():
    import inspect

    source = inspect.getsource(BaseGraphStorage)
    assert "await asyncio.gather(" not in source
    assert source.count("_bounded_gather") >= 5
