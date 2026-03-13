import os

import numpy as np

from lightrag.llm.azure_openai import azure_openai_complete_if_cache, azure_openai_embed
from lightrag.utils import wrap_embedding_func_with_attrs

extra_headers = {
    "client_id": os.getenv("NESGEN_CLIENT_ID", ""),
    "client_secret": os.getenv("NESGEN_CLIENT_SECRET", ""),
}


# Define LLM model function
def llm_model_func(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
):
    kwargs["extra_headers"] = extra_headers
    return azure_openai_complete_if_cache(
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
    return await azure_openai_embed.func(
        texts,
        model=os.getenv("EMBEDDING_MODEL"),
        api_key=os.getenv("EMBEDDING_API_KEY"),
        base_url=os.getenv("EMBEDDING_BINDING_HOST"),
        client_configs={"default_headers": extra_headers},
    )
