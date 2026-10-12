import os
from uuid import uuid4

import httpx
import numpy as np

from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.rerank import cohere_rerank
from lightrag.tools.kong_api_client.kong_client import KongClient
from lightrag.utils import wrap_embedding_func_with_attrs

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
    # One client per call on purpose: the OpenAI wrapper closes the client it
    # was given when the call finishes, so a shared instance would be closed
    # after its first use.
    return httpx.AsyncClient(http2=True, verify=_verify_ssl("PROXY_VERIFY_SSL"))


# Define LLM model function
def llm_model_func(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
):
    kwargs["extra_headers"] = {
        "Authorization": f"Bearer {kong_client.generate_token()}"
    }
    kwargs["extra_body"] = extra_body
    kwargs["openai_client_configs"] = {"http_client": new_httpx_client()}
    return openai_complete_if_cache(
        os.getenv("LLM_MODEL"),
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=os.getenv("LLM_BINDING_API_KEY"),
        base_url=os.getenv("LLM_BINDING_HOST"),
        **kwargs,
    )


@wrap_embedding_func_with_attrs(
    embedding_dim=int(os.getenv("EMBEDDING_DIM", "3072")),
    max_token_size=8192,
    model_name=os.getenv("EMBEDDING_MODEL"),
)
async def embedding_func(texts: list[str]) -> np.ndarray:
    return await openai_embed.func(
        texts,
        model=os.getenv("EMBEDDING_MODEL"),
        api_key=os.getenv("EMBEDDING_API_KEY"),
        base_url=os.getenv("EMBEDDING_BINDING_HOST"),
        client_configs={"http_client": new_httpx_client()},
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
