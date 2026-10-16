"""``http_client`` supplied as a factory gets a fresh client per attempt.

The SDK client closes the httpx client it was given when an attempt ends, and
the tenacity retry loop re-invokes the function with the caller's original
kwargs. A single shared ``http_client`` instance is therefore already closed
on the second attempt, turning every transient failure into
"Cannot send a request, as the client has been closed." on all retries.
"""

import httpx
import pytest
from tenacity import wait_none

from lightrag.llm.openai import create_openai_async_client, openai_complete_if_cache

_COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "OK"},
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


def _flaky_transport():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("transient blip", request=request)
        return httpx.Response(200, json=_COMPLETION)

    return httpx.MockTransport(handler), calls


@pytest.mark.offline
def test_factory_builds_a_new_http_client_per_sdk_client():
    created = []

    def factory():
        client = httpx.AsyncClient()
        created.append(client)
        return client

    first = create_openai_async_client(
        api_key="k", base_url="http://gw/v1", client_configs={"http_client": factory}
    )
    second = create_openai_async_client(
        api_key="k", base_url="http://gw/v1", client_configs={"http_client": factory}
    )

    assert len(created) == 2
    assert first._client is created[0]
    assert second._client is created[1]


@pytest.mark.offline
@pytest.mark.asyncio
async def test_retry_after_connection_error_uses_fresh_http_client():
    transport, calls = _flaky_transport()
    created = []

    def factory():
        client = httpx.AsyncClient(transport=transport)
        created.append(client)
        return client

    complete = openai_complete_if_cache.retry_with(wait=wait_none())
    result = await complete(
        model="test-model",
        prompt="ping",
        api_key="k",
        base_url="http://gw/v1",
        openai_client_configs={"http_client": factory},
    )

    assert result == "OK"
    assert calls["n"] == 2
    assert len(created) == 2
    assert all(c.is_closed for c in created)
