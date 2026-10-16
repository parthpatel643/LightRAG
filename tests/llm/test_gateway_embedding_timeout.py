"""Gateway embedding calls must time out per request.

Without a client timeout the OpenAI SDK waits up to 600s on a dropped
connection, so the priority-queue worker (2 x EMBEDDING_TIMEOUT) kills the
call before openai_embed's retries can run, failing the whole document merge.
"""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

pytestmark = pytest.mark.offline


@pytest.fixture
def functions(monkeypatch):
    kong = ModuleType("lightrag.tools.kong_api_client.kong_client")
    kong.KongClient = lambda **_: SimpleNamespace(generate_token=lambda: "token")
    monkeypatch.setitem(sys.modules, "lightrag.tools.kong_api_client.kong_client", kong)
    monkeypatch.delitem(sys.modules, "lightrag.functions", raising=False)
    return importlib.import_module("lightrag.functions")


@pytest.mark.asyncio
@pytest.mark.parametrize("env_value, expected", [(None, 15.0), ("90", 45.0)])
async def test_embedding_requests_time_out_within_the_worker_budget(
    functions, monkeypatch, env_value, expected
):
    if env_value is None:
        monkeypatch.delenv("EMBEDDING_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("EMBEDDING_TIMEOUT", env_value)
    seen = {}

    async def fake_embed(texts, **kwargs):
        seen.update(kwargs)
        return np.zeros((len(texts), 3))

    monkeypatch.setattr(functions.openai_embed, "func", fake_embed)
    await functions.embedding_func.func(["a"])

    configs = seen["client_configs"]
    assert configs["timeout"] == expected
    assert callable(configs["http_client"])
    # Three attempts plus openai_embed's 4s/8s backoff fit in 2 x EMBEDDING_TIMEOUT.
    assert 3 * configs["timeout"] + 12 < 2 * float(env_value or 30)
