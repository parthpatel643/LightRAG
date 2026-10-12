"""A request naming another workspace is refused instead of served from the wrong data."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.offline


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in (
        "LLM_BINDING",
        "EMBEDDING_BINDING",
        "LLM_BINDING_HOST",
        "LLM_MODEL",
        "EMBEDDING_BINDING_HOST",
        "CORS_ORIGINS",
        "LIGHTRAG_API_PREFIX",
        "AUTH_ACCOUNTS",
        "LIGHTRAG_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_BINDING", "ollama")
    monkeypatch.setenv("EMBEDDING_BINDING", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3:latest")

    import lightrag.api.config as config

    config._global_args = None
    config._initialized = False
    yield
    config._global_args = None
    config._initialized = False


def _client(monkeypatch, workspace="alpha", enforce=None):
    from lightrag.api.config import initialize_config, parse_args

    if enforce is not None:
        monkeypatch.setenv("LIGHTRAG_ENFORCE_WORKSPACE_HEADER", enforce)
    original = sys.argv.copy()
    try:
        sys.argv = ["lightrag-server"]
        args = parse_args()
    finally:
        sys.argv = original
    initialize_config(args, force=True)

    with patch("lightrag.api.lightrag_server.LightRAG") as mock_rag:
        mock_rag.return_value = MagicMock(workspace=workspace)
        from lightrag.api.lightrag_server import create_app

        app = create_app(args)
    return TestClient(app)


def test_mismatched_workspace_header_is_refused(monkeypatch):
    response = _client(monkeypatch).get(
        "/documents/status_counts", headers={"LIGHTRAG-WORKSPACE": "beta"}
    )
    assert response.status_code == 409
    assert "beta" in response.json()["detail"] and "alpha" in response.json()["detail"]


def test_matching_header_is_not_refused(monkeypatch):
    response = _client(monkeypatch).get(
        "/documents/status_counts", headers={"LIGHTRAG-WORKSPACE": "alpha"}
    )
    assert response.status_code != 409


def test_header_is_sanitised_like_the_server_does(monkeypatch):
    response = _client(monkeypatch, workspace="sea_cabin").get(
        "/documents/status_counts", headers={"LIGHTRAG-WORKSPACE": "sea cabin"}
    )
    assert response.status_code != 409


def test_unguarded_paths_ignore_the_header(monkeypatch):
    response = _client(monkeypatch).get("/health", headers={"LIGHTRAG-WORKSPACE": "beta"})
    # /health is not a guarded path; whatever it answers, it is not the 409.
    assert response.status_code != 409


def test_no_header_means_no_check(monkeypatch):
    assert _client(monkeypatch).get("/documents/status_counts").status_code != 409


def test_enforcement_can_be_disabled(monkeypatch):
    response = _client(monkeypatch, enforce="false").get(
        "/documents/status_counts", headers={"LIGHTRAG-WORKSPACE": "beta"}
    )
    assert response.status_code != 409
