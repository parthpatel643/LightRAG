import os
from uuid import uuid4

import httpx
import numpy as np

from lightrag.generate_token import provide_bearer_token
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.rerank import cohere_rerank
from lightrag.utils import wrap_embedding_func_with_attrs

extra_body = {"extra_body": {"trace_data": {"session_id": str(uuid4())}}}


def new_httpx_client():
    # Create a new client per call; adjust options as needed
    return httpx.AsyncClient(http2=True, verify=False)


# Define LLM model function
def llm_model_func(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
):
    kwargs["extra_headers"] = provide_bearer_token()
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
            "extra_headers": provide_bearer_token(),
            "extra_body": extra_body,
        },
    )


def rerank_model_func(*args, **kwargs):
    return cohere_rerank(
        *args,
        model=os.getenv("RERANK_MODEL"),
        api_key=provide_bearer_token()["Authorization"].split(" ")[1],
        base_url=os.getenv("RERANK_BINDING_HOST"),
        extra_body=extra_body,
        **kwargs,
    )
