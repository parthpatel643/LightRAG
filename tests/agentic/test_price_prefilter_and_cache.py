"""Pricing lookup: lexical gate in front of the LLM, and a short result cache."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from lightrag.agentic import price_line_items as pli

pytestmark = pytest.mark.offline


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    monkeypatch.setattr(pli, "_price_cache", {})
    monkeypatch.delenv("PRICING_INTENT_PREFILTER", raising=False)
    monkeypatch.delenv("PRICE_CACHE_TTL_SECONDS", raising=False)


@pytest.mark.parametrize(
    "query",
    [
        "What is the rate for cabin cleaning?",
        "how much does lavatory service cost",
        "Any surcharge for night turns?",
        "price per turn at BOS",
        "fee is $120",
    ],
)
def test_money_words_pass_the_gate(query):
    assert pli._might_be_pricing_query(query) is True


@pytest.mark.parametrize(
    "query",
    ["Who performs ground handling?", "What is included in cabin cleaning?"],
)
def test_other_questions_skip_the_classifier(query):
    assert pli._might_be_pricing_query(query) is False


@pytest.mark.asyncio
async def test_non_pricing_query_never_calls_the_llm(monkeypatch):
    classify = AsyncMock(return_value=True)
    monkeypatch.setattr(pli, "classify_pricing_intent", classify)
    assert await pli.get_price_context("Who performs ground handling?", {}) == ""
    classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PRICING_INTENT_PREFILTER", "false")
    classify = AsyncMock(return_value=False)
    monkeypatch.setattr(pli, "classify_pricing_intent", classify)
    await pli.get_price_context("Who performs ground handling?", {})
    classify.assert_awaited_once()


@pytest.mark.asyncio
async def test_rows_are_cached_per_workspace_and_keywords(monkeypatch):
    monkeypatch.setattr(pli, "classify_pricing_intent", AsyncMock(return_value=True))
    fetch = AsyncMock(return_value=[{"unit_price": 10}])
    monkeypatch.setattr(pli, "fetch_price_line_items", fetch)

    first = await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    second = await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    other = await pli.get_price_context("rate for cabin cleaning", {"workspace": "w2"})

    assert first == second and first.startswith("<price_line_items>")
    assert other == first
    assert fetch.await_count == 2  # w1 once (cached), w2 once


@pytest.mark.asyncio
async def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PRICE_CACHE_TTL_SECONDS", "0")
    monkeypatch.setattr(pli, "classify_pricing_intent", AsyncMock(return_value=True))
    fetch = AsyncMock(return_value=[{"unit_price": 10}])
    monkeypatch.setattr(pli, "fetch_price_line_items", fetch)
    await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_empty_results_are_not_cached(monkeypatch):
    monkeypatch.setattr(pli, "classify_pricing_intent", AsyncMock(return_value=True))
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(pli, "fetch_price_line_items", fetch)
    await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    await pli.get_price_context("rate for cabin cleaning", {"workspace": "w1"})
    assert fetch.await_count == 2
