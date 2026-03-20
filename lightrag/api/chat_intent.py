"""
LLM-based intent classifier for chat routing.

Classifies each user message into one of four intents:
  - rag_query      : requires knowledge-base retrieval
  - chit_chat      : casual conversation / greetings / thanks
  - memory_recall  : user asks about current conversation history
  - out_of_scope   : clearly off-domain question

For memory_recall and out_of_scope, a direct response is also synthesised
so the route handler does not need a second LLM call.
"""

import inspect
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from lightrag.utils import get_env_value, logger

# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

INTENT_ENABLED_DEFAULT: bool = (
    get_env_value("CHAT_INTENT_ENABLED", "true", str).lower() != "false"
)

# Domain label shown in the classification prompt.  Override with env var.
_DOMAIN_LABEL: str = os.getenv("CHAT_DOMAIN_LABEL", "knowledge base")


class Intent(str, Enum):
    RAG_QUERY = "rag_query"
    CHIT_CHAT = "chit_chat"
    MEMORY_RECALL = "memory_recall"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class IntentResult:
    intent: Intent
    direct_response: Optional[str] = None
    """Pre-built answer for memory_recall / out_of_scope intents.
    None for rag_query and chit_chat."""


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_CLASSIFICATION_SYSTEM_PROMPT = """\
You are an intent classifier for a {domain} knowledge assistant.
Classify the following user message into exactly one of:
  - rag_query: a question that requires searching the knowledge base
  - chit_chat: casual conversation, greetings, thanks, or general questions \
unrelated to the domain
  - memory_recall: the user is asking about the current conversation history \
(e.g. "What did I ask?", "What have we discussed?", "Remind me what I asked earlier")
  - out_of_scope: the topic is clearly outside the domain and should not be answered

Conversation so far (last 3 turns):
{last_turns}

User message: "{query}"

Respond with JSON only (no markdown, no explanation):
{{"intent": "<intent>", "response": "<direct_response_if_not_rag_query>"}}

Rules:
- For rag_query and chit_chat, set "response" to null.
- For out_of_scope, provide a polite single-sentence refusal in "response".
- For memory_recall, synthesise a brief answer from the conversation history \
shown above in "response".\
"""


def _format_last_turns(history: List[Dict[str, str]], n_turns: int = 3) -> str:
    """Return the last *n_turns* conversation turns as a readable string."""
    if not history:
        return "(no conversation history yet)"
    # Each turn is 2 messages (user + assistant); take last n_turns * 2 messages
    recent = history[-(n_turns * 2):]
    lines = []
    for msg in recent:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> dict:
    """Best-effort JSON parser: tries direct parse, fence stripping, and brace extraction.

    Handles:
    - Clean JSON strings
    - Markdown code-fenced JSON (```json ... ```)
    - Prose-wrapped responses where the JSON object appears anywhere in the text
    """
    text = raw.strip()

    # 1. Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip ``` code fences (fence may appear anywhere, not just at the start)
    if "```" in text:
        lines = text.splitlines()
        inner, in_fence = [], False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            inner.append(line)
        fenced_text = "\n".join(inner).strip()
        try:
            return json.loads(fenced_text)
        except json.JSONDecodeError:
            pass

    # 3. Extract the first complete {...} block (handles prose-wrapped responses)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text!r}")


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

async def classify_intent(
    query: str,
    history: List[Dict[str, str]],
    rag,
) -> IntentResult:
    """Classify *query* into an Intent using a single LLM call via *rag*.

    Falls back to Intent.RAG_QUERY on any error so that the system degrades
    gracefully rather than blocking the user.
    """
    last_turns_text = _format_last_turns(history)
    prompt = _CLASSIFICATION_SYSTEM_PROMPT.format(
        domain=_DOMAIN_LABEL,
        last_turns=last_turns_text,
        query=query,
    )

    try:
        raw_response = await rag.llm_model_func(
            prompt,
            system_prompt=None,
            history_messages=[],
            stream=False,
        )

        # Guard: some LLM bindings return an async generator even when stream=False
        # is passed (e.g. if the underlying function ignores the kwarg).  Collect it.
        if inspect.isasyncgen(raw_response):
            logger.warning(
                "[IntentClassifier] llm_model_func returned an async generator "
                "despite stream=False — collecting chunks."
            )
            chunks = []
            async for chunk in raw_response:
                if isinstance(chunk, str):
                    chunks.append(chunk)
                elif hasattr(chunk, "choices"):
                    for choice in chunk.choices:
                        delta = getattr(choice, "delta", None)
                        if delta and getattr(delta, "content", None):
                            chunks.append(delta.content)
            raw_response = "".join(chunks)

        logger.debug(f"[IntentClassifier] Raw LLM response: {raw_response!r}")

        parsed = _parse_llm_json(raw_response)

        intent_str = parsed.get("intent", "rag_query").strip().lower()
        direct_response = parsed.get("response") or None

        # Validate intent value; fall back to rag_query if unrecognised
        try:
            intent = Intent(intent_str)
        except ValueError:
            logger.warning(
                f"[IntentClassifier] Unrecognised intent '{intent_str}', "
                "falling back to rag_query"
            )
            intent = Intent.RAG_QUERY

        logger.debug(
            f"[IntentClassifier] '{query[:60]}' → {intent.value}"
        )
        return IntentResult(intent=intent, direct_response=direct_response)

    except Exception as exc:
        logger.error(
            f"[IntentClassifier] Classification failed: {exc}. "
            "Falling back to rag_query.",
            exc_info=True,
        )
        return IntentResult(intent=Intent.RAG_QUERY)
