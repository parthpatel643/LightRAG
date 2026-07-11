"""Regression tests for role-level LLM function selection in create_app().

Bug: create_app() previously built role_llm_configs unconditionally via
create_role_llm_func() for every role (extract/keyword/query/vlm), even when
a custom_llm_func from functions.py was available and the role's effective
binding/model/host/api_key were identical to the base LLM config. This meant
any custom transport configured on custom_llm_func (e.g. a verify=False
httpx client required for a proxy with a self-signed certificate) was never
applied to role-scoped LLM calls, which are used for every actual query
(extract/keyword/query roles all fire per-request). The base llm_model_func
itself did use custom_llm_func correctly, so the bug was invisible outside a
running API server hitting /query.

Fix: _select_role_llm_func() in lightrag_server.py reuses custom_llm_func for
any role whose resolved binding/model/host/api_key exactly match the base
config (i.e. is_cross_provider is False and there is no role-specific
model/host/api_key override), and only falls back to the generic
create_role_llm_func() client when a role genuinely diverges from the base
provider config.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

_ENV_VARS_TO_ISOLATE = (
    "LLM_BINDING",
    "EMBEDDING_BINDING",
    "LLM_BINDING_HOST",
    "LLM_BINDING_API_KEY",
    "LLM_MODEL",
    "EMBEDDING_BINDING_HOST",
    "EMBEDDING_BINDING_API_KEY",
    "EMBEDDING_MODEL",
    "RERANK_BINDING",
    "EXTRACT_LLM_BINDING",
    "EXTRACT_LLM_MODEL",
    "EXTRACT_LLM_BINDING_HOST",
    "EXTRACT_LLM_BINDING_API_KEY",
    "KEYWORD_LLM_BINDING",
    "KEYWORD_LLM_MODEL",
    "KEYWORD_LLM_BINDING_HOST",
    "KEYWORD_LLM_BINDING_API_KEY",
    "QUERY_LLM_BINDING",
    "QUERY_LLM_MODEL",
    "QUERY_LLM_BINDING_HOST",
    "QUERY_LLM_BINDING_API_KEY",
    "VLM_LLM_BINDING",
    "VLM_LLM_MODEL",
    "VLM_LLM_BINDING_HOST",
    "VLM_LLM_BINDING_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Isolate tests from developer-local .env pollution.

    Uses azure_openai for LLM_BINDING (the binding whose role construction
    path this bug affects) and ollama for embeddings so create_app's
    embedding function construction doesn't need real credentials.
    """
    for var in _ENV_VARS_TO_ISOLATE:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_BINDING", "azure_openai")
    monkeypatch.setenv("LLM_MODEL", "base-model")
    monkeypatch.setenv("LLM_BINDING_HOST", "https://proxy.example.com/")
    monkeypatch.setenv("LLM_BINDING_API_KEY", "base-key")
    monkeypatch.setenv("EMBEDDING_BINDING", "ollama")


@pytest.fixture
def fake_custom_llm_func(monkeypatch):
    """Inject a fake lightrag.functions module exposing a sentinel LLM func.

    create_app() imports functions.py locally (inside the function body) on
    every call, so swapping sys.modules["lightrag.functions"] for the
    duration of a test is sufficient to control what create_app() sees as
    `custom_llm_func`, without needing the real module's AWS/Kong-backed
    client construction.
    """
    module = types.ModuleType("lightrag.functions")
    sentinel_llm_func = MagicMock(name="custom_llm_func")
    module.llm_model_func = sentinel_llm_func
    module.embedding_func = MagicMock(name="custom_embedding_func")
    module.rerank_model_func = MagicMock(name="custom_rerank_func")
    monkeypatch.setitem(sys.modules, "lightrag.functions", module)
    return sentinel_llm_func


def _make_args():
    from lightrag.api.config import parse_args

    original_argv = sys.argv.copy()
    try:
        sys.argv = ["lightrag-server"]
        return parse_args()
    finally:
        sys.argv = original_argv


def _build_role_llm_configs(args):
    """Invoke create_app() with LightRAG mocked out and return the
    role_llm_configs kwarg it was constructed with.

    global_args is a lazy proxy (see lightrag.api.config._GlobalArgsProxy)
    that re-parses sys.argv on first access if not explicitly initialized.
    Importing lightrag.api.lightrag_server for the first time triggers a
    module-level `auth_handler = AuthHandler()` that touches global_args, so
    we must force-initialize it with our test args before that import can
    happen under pytest's own sys.argv.
    """
    from lightrag.api.config import initialize_config

    initialize_config(args, force=True)

    with patch("lightrag.api.lightrag_server.LightRAG") as mock_rag:
        mock_rag.return_value = MagicMock()
        from lightrag.api.lightrag_server import create_app

        create_app(args)
        return mock_rag.call_args.kwargs["role_llm_configs"]


class TestRoleLLMFuncReusesCustomLLMFunc:
    """Every role should reuse custom_llm_func when it isn't cross-provider
    and has no role-specific model/host/api_key override."""

    def test_all_roles_reuse_custom_llm_func_by_default(self, fake_custom_llm_func):
        args = _make_args()
        role_configs = _build_role_llm_configs(args)

        for role in ("extract", "keyword", "query", "vlm"):
            assert role_configs[role].func is fake_custom_llm_func, (
                f"role '{role}' should reuse custom_llm_func when its "
                "binding/model/host/api_key match the base LLM config"
            )

    def test_role_with_overridden_model_falls_back_to_generic_func(
        self, monkeypatch, fake_custom_llm_func
    ):
        monkeypatch.setenv("QUERY_LLM_MODEL", "some-other-model")
        args = _make_args()
        role_configs = _build_role_llm_configs(args)

        assert role_configs["query"].func is not fake_custom_llm_func
        # Unaffected roles still reuse the custom func.
        assert role_configs["extract"].func is fake_custom_llm_func
        assert role_configs["keyword"].func is fake_custom_llm_func
        assert role_configs["vlm"].func is fake_custom_llm_func

    def test_role_with_overridden_host_falls_back_to_generic_func(
        self, monkeypatch, fake_custom_llm_func
    ):
        monkeypatch.setenv("EXTRACT_LLM_BINDING_HOST", "https://other-proxy.example.com/")
        args = _make_args()
        role_configs = _build_role_llm_configs(args)

        assert role_configs["extract"].func is not fake_custom_llm_func
        assert role_configs["query"].func is fake_custom_llm_func

    def test_cross_provider_role_falls_back_to_generic_func(
        self, monkeypatch, fake_custom_llm_func
    ):
        monkeypatch.setenv("VLM_LLM_BINDING", "openai")
        monkeypatch.setenv("VLM_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("VLM_LLM_BINDING_HOST", "https://api.openai.com/v1")
        monkeypatch.setenv("VLM_LLM_BINDING_API_KEY", "vlm-key")
        args = _make_args()
        role_configs = _build_role_llm_configs(args)

        assert role_configs["vlm"].func is not fake_custom_llm_func
        assert role_configs["vlm"].metadata["is_cross_provider"] is True
        assert role_configs["query"].func is fake_custom_llm_func

    def test_no_custom_llm_func_uses_generic_func_for_every_role(self, monkeypatch):
        """When functions.py isn't importable, behavior is unchanged: every
        role gets its own generic provider client."""
        monkeypatch.setitem(sys.modules, "lightrag.functions", None)
        args = _make_args()
        role_configs = _build_role_llm_configs(args)

        funcs = {role_configs[role].func for role in ("extract", "keyword", "query", "vlm")}
        assert len(funcs) == 4
        assert all(callable(func) for func in funcs)
