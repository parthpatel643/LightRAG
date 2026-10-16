"""Gateway LLM calls refused by the provider's content policy can fall back.

Azure OpenAI refuses some routine contract questions outright (e.g. the word
"escort" in a wheelchair-escort rate question), so the query returned "No
relevant context found". With LLM_CONTENT_FILTER_FALLBACK_MODEL set, only such
refusals are retried on the fallback model; everything else is unchanged.
"""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.offline

FILTERED = (
    "Error code: 400 - The response was filtered due to the prompt triggering "
    "Azure OpenAI's content management policy."
)


@pytest.fixture
def functions(monkeypatch):
    kong = ModuleType("lightrag.tools.kong_api_client.kong_client")
    kong.KongClient = lambda **_: SimpleNamespace(generate_token=lambda: "token")
    monkeypatch.setitem(sys.modules, "lightrag.tools.kong_api_client.kong_client", kong)
    monkeypatch.delitem(sys.modules, "lightrag.functions", raising=False)
    module = importlib.import_module("lightrag.functions")
    monkeypatch.setenv("LLM_MODEL", "GPT-5.6-Luna")
    return module


def _fake_completion(models: list, error: str = FILTERED):
    async def fake(model, prompt, **kwargs):
        models.append(model)
        if model == "GPT-5.6-Luna":
            raise RuntimeError(error)
        return f"answer from {model}"

    return fake


@pytest.mark.asyncio
async def test_content_filtered_call_is_retried_on_fallback_model(functions, monkeypatch):
    models: list = []
    monkeypatch.setattr(functions, "openai_complete_if_cache", _fake_completion(models))
    monkeypatch.setenv("LLM_CONTENT_FILTER_FALLBACK_MODEL", "Claude-Sonnet-4.6")

    result = await functions.llm_model_func("escort rate?")

    assert result == "answer from Claude-Sonnet-4.6"
    assert models == ["GPT-5.6-Luna", "Claude-Sonnet-4.6"]


@pytest.mark.asyncio
async def test_without_fallback_the_refusal_propagates(functions, monkeypatch):
    models: list = []
    monkeypatch.setattr(functions, "openai_complete_if_cache", _fake_completion(models))
    monkeypatch.delenv("LLM_CONTENT_FILTER_FALLBACK_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="content management policy"):
        await functions.llm_model_func("escort rate?")


@pytest.mark.asyncio
async def test_other_errors_are_not_rerouted(functions, monkeypatch):
    models: list = []
    monkeypatch.setattr(
        functions, "openai_complete_if_cache", _fake_completion(models, "Connection error")
    )
    monkeypatch.setenv("LLM_CONTENT_FILTER_FALLBACK_MODEL", "Claude-Sonnet-4.6")

    with pytest.raises(RuntimeError, match="Connection error"):
        await functions.llm_model_func("q")
    assert models == ["GPT-5.6-Luna"]
