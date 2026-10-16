"""Content-block responses from OpenAI-compatible gateways.

Some gateways that front Claude models (e.g. Claude Sonnet 5.5 with adaptive
thinking) return ``message.content`` as a list of content blocks instead of a
string: a redacted ``thinking_block`` followed by the ``text`` block that
carries the actual answer. The OpenAI SDK does not validate response models,
so the list reaches ``openai_complete_if_cache`` unchanged.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from lightrag.llm.openai import InvalidResponseError, openai_complete_if_cache


def _thinking_block(text: str = "") -> dict:
    return {
        "type": "thinking_block",
        "thinking_block": {
            "reasoningContent": {
                "reasoningText": {"text": text, "signature": "CAQS2Q0KEggSEAEYAjgB"}
            }
        },
    }


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _make_completion(content, reasoning_content: str = ""):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=content,
                    parsed=None,
                    reasoning_content=reasoning_content,
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


def _make_fake_client(result):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=result))
        ),
        close=AsyncMock(),
    )


class _FakeAsyncStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration

    async def aclose(self):
        return None


def _make_stream_chunk(content=None, reasoning_content=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content, reasoning_content=reasoning_content
                )
            )
        ]
    )


async def _complete(content, **kwargs):
    fake_client = _make_fake_client(_make_completion(content))
    with patch(
        "lightrag.llm.openai.create_openai_async_client", return_value=fake_client
    ):
        return await openai_complete_if_cache(
            model="test-model", prompt="Extract entities", **kwargs
        )


@pytest.mark.offline
@pytest.mark.asyncio
async def test_thinking_then_text_blocks_return_text():
    """Exact shape returned by the gateway for Claude Sonnet 5.5 gleaning calls."""
    answer = '{"entities": [], "relationships": []}'
    result = await _complete(
        [_thinking_block(), _text_block(answer)],
        response_format={"type": "json_object"},
    )
    assert result == answer
    assert isinstance(result, str)


@pytest.mark.offline
@pytest.mark.asyncio
async def test_multiple_text_blocks_are_concatenated():
    result = await _complete(
        [_thinking_block(), _text_block('{"entities": '), _text_block("[]}")]
    )
    assert result == '{"entities": []}'


@pytest.mark.offline
@pytest.mark.asyncio
async def test_thinking_only_blocks_raise_invalid_response_with_reasoning_hint():
    """No text block must surface as the documented empty-content error, not
    an ``AttributeError`` from calling ``.strip()`` on a list."""
    fake_client = _make_fake_client(
        _make_completion([_thinking_block("weighing the clauses...")])
    )
    with patch(
        "lightrag.llm.openai.create_openai_async_client", return_value=fake_client
    ):
        # Undecorated coroutine: one attempt, no tenacity retries/backoff.
        with pytest.raises(InvalidResponseError) as excinfo:
            await openai_complete_if_cache.__wrapped__(
                model="test-model", prompt="Extract entities"
            )

    assert "reasoning-only" in str(excinfo.value)
    assert "reasoning_content_len=23" in str(excinfo.value)


@pytest.mark.offline
@pytest.mark.asyncio
async def test_thinking_block_text_feeds_cot_when_no_text_block():
    result = await _complete(
        [_thinking_block("weighing the clauses...")], enable_cot=True
    )
    assert result == "<think>weighing the clauses...</think>"


@pytest.mark.offline
@pytest.mark.asyncio
async def test_streaming_delta_content_blocks_yield_text():
    fake_stream = _FakeAsyncStream(
        [
            _make_stream_chunk(content=[_thinking_block()]),
            _make_stream_chunk(content=[_text_block('{"answer":')]),
            _make_stream_chunk(content=[_text_block('"ok"}')]),
        ]
    )
    fake_client = _make_fake_client(fake_stream)
    with patch(
        "lightrag.llm.openai.create_openai_async_client", return_value=fake_client
    ):
        stream = await openai_complete_if_cache(
            model="test-model", prompt="Extract entities", stream=True
        )
        chunks = [chunk async for chunk in stream]

    assert all(isinstance(c, str) for c in chunks)
    assert "".join(chunks) == '{"answer":"ok"}'
