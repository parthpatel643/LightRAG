"""Judge temperature for the semantic-equivalence evaluator.

Reasoning models such as GPT-5.6-Luna only accept their default temperature
and reject the judge's deterministic ``temperature=0`` with a 400.
``EVAL_JUDGE_TEMPERATURE=default`` omits the parameter for them.
"""

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.offline


@pytest.fixture
def evaluator_module(monkeypatch):
    calls = []

    async def fake_llm(**kwargs):
        calls.append(kwargs)
        return json.dumps({"score": 1.0, "reasoning": "same"})

    # lightrag.functions fetches a gateway secret from AWS at import time.
    monkeypatch.setitem(
        sys.modules, "lightrag.functions", SimpleNamespace(llm_model_func=fake_llm)
    )
    monkeypatch.delitem(
        sys.modules, "lightrag.evaluation.semantic_equivalence_evaluator", raising=False
    )
    module = importlib.import_module("lightrag.evaluation.semantic_equivalence_evaluator")
    return module, calls


async def _judge(module):
    evaluator = module.SemanticEquivalenceEvaluator.__new__(
        module.SemanticEquivalenceEvaluator
    )
    evaluator.pass_threshold = 0.7
    return await evaluator._calculate_semantic_equivalence("q", "a", "a")


@pytest.mark.asyncio
async def test_judge_defaults_to_temperature_zero(evaluator_module, monkeypatch):
    module, calls = evaluator_module
    monkeypatch.delenv("EVAL_JUDGE_TEMPERATURE", raising=False)
    await _judge(module)
    assert calls[-1]["temperature"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["default", "none", ""])
async def test_judge_temperature_can_be_omitted(evaluator_module, monkeypatch, value):
    module, calls = evaluator_module
    monkeypatch.setenv("EVAL_JUDGE_TEMPERATURE", value)
    await _judge(module)
    assert "temperature" not in calls[-1]


@pytest.mark.asyncio
async def test_judge_temperature_accepts_a_number(evaluator_module, monkeypatch):
    module, calls = evaluator_module
    monkeypatch.setenv("EVAL_JUDGE_TEMPERATURE", "1")
    await _judge(module)
    assert calls[-1]["temperature"] == 1.0


FILTERED = (
    "Error code: 400 - The response was filtered due to the prompt triggering "
    "Azure OpenAI's content management policy."
)


@pytest.fixture
def filtering_judge(evaluator_module, monkeypatch):
    """Primary judge rejects the prompt; any explicit llm_model answers."""
    module, _ = evaluator_module
    calls = []

    async def fake_llm(**kwargs):
        calls.append(kwargs)
        if not kwargs.get("llm_model"):
            raise RuntimeError(FILTERED)
        return json.dumps({"score": 5, "reasoning": "same"})

    monkeypatch.setattr(module, "llm_model_func", fake_llm)
    return module, calls


@pytest.mark.asyncio
async def test_content_filtered_judge_falls_back_to_configured_model(
    filtering_judge, monkeypatch
):
    module, calls = filtering_judge
    monkeypatch.setenv("EVAL_JUDGE_FALLBACK_MODEL", "Claude-Sonnet-4.6")

    result = await _judge(module)

    assert result["score"] == 1.0
    assert result["judge_model"] == "Claude-Sonnet-4.6"
    assert calls[-1]["llm_model"] == "Claude-Sonnet-4.6"


@pytest.mark.asyncio
async def test_content_filtered_judge_without_fallback_is_reported_as_error(
    filtering_judge, monkeypatch
):
    module, _ = filtering_judge
    monkeypatch.delenv("EVAL_JUDGE_FALLBACK_MODEL", raising=False)

    result = await _judge(module)

    assert result["score"] == 0.0
    assert result["reasoning"].startswith("Error:")
