import os
from uuid import uuid4

import httpx
import numpy as np

from lightrag.llm._error_utils import is_content_filter_error
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.rerank import cohere_rerank
from lightrag.tools.kong_api_client.kong_client import KongClient
from lightrag.utils import logger, wrap_embedding_func_with_attrs

kong_client = KongClient(
    region_name="us-east-1",
    user_secret_manager_name="bos-line-stations-proxy-service-api-key",
)

extra_body = {"extra_body": {"trace_data": {"session_id": str(uuid4())}}}


def _verify_ssl(env_name: str) -> bool:
    """TLS verification is on unless explicitly disabled for an internal proxy
    with a self-signed certificate (``<env_name>=false``)."""
    return os.getenv(env_name, "true").strip().lower() not in {"0", "false", "no", "off"}


def new_httpx_client():
    # Passed as a factory (not an instance): the OpenAI wrapper closes the
    # client it was given when each attempt finishes, so a shared instance
    # would already be closed when tenacity retries the call.
    return httpx.AsyncClient(http2=True, verify=_verify_ssl("PROXY_VERIFY_SSL"))


# Define LLM model function
async def llm_model_func(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
):
    # Optional per-call model override (e.g. an evaluation judge fallback).
    model = kwargs.pop("llm_model", None) or os.getenv("LLM_MODEL")
    kwargs["extra_headers"] = {
        "Authorization": f"Bearer {kong_client.generate_token()}"
    }
    kwargs["extra_body"] = extra_body
    kwargs["openai_client_configs"] = {"http_client": new_httpx_client}

    async def call(target_model):
        return await openai_complete_if_cache(
            target_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=os.getenv("LLM_BINDING_API_KEY"),
            base_url=os.getenv("LLM_BINDING_HOST"),
            **kwargs,
        )

    try:
        return await call(model)
    except Exception as error:
        # Only a provider content-policy refusal is rerouted, and only when a
        # fallback model is configured; every other failure propagates.
        fallback = os.getenv("LLM_CONTENT_FILTER_FALLBACK_MODEL", "").strip()
        if not fallback or fallback == model or not is_content_filter_error(error):
            raise
        logger.warning(f"{model} refused the prompt (content policy); using {fallback}")
        return await call(fallback)


@wrap_embedding_func_with_attrs(
    embedding_dim=int(os.getenv("EMBEDDING_DIM", "3072")),
    max_token_size=8192,
    model_name=os.getenv("EMBEDDING_MODEL"),
)
async def embedding_func(texts: list[str]) -> np.ndarray:
    # Each request gets half of EMBEDDING_TIMEOUT: the SDK default (600s) would
    # let one dropped connection outlast the queue worker (2 x EMBEDDING_TIMEOUT),
    # which then kills the call before openai_embed's retries can run.
    request_timeout = float(os.getenv("EMBEDDING_TIMEOUT", "30")) / 2
    return await openai_embed.func(
        texts,
        model=os.getenv("EMBEDDING_MODEL"),
        api_key=os.getenv("EMBEDDING_API_KEY"),
        base_url=os.getenv("EMBEDDING_BINDING_HOST"),
        client_configs={"http_client": new_httpx_client, "timeout": request_timeout},
        extra_configs={
            "extra_headers": {
                "Authorization": f"Bearer {kong_client.generate_token()}"
            },
            "extra_body": extra_body,
        },
    )


def rerank_model_func(*args, **kwargs):
    kwargs.setdefault("verify_ssl", _verify_ssl("RERANK_VERIFY_SSL"))
    return cohere_rerank(
        *args,
        model=os.getenv("RERANK_MODEL"),
        api_key=kong_client.generate_token(),
        base_url=os.getenv("RERANK_BINDING_HOST"),
        extra_body=extra_body,
        **kwargs,
    )
