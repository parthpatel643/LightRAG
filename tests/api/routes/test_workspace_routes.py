"""Workspace routes: authenticated, validated, serialised."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
workspace_routes = importlib.import_module("lightrag.api.routers.workspace_routes")
sys.argv = _original_argv

pytestmark = pytest.mark.offline

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    working = tmp_path / "rag_storage"
    inputs = tmp_path / "inputs"
    working.mkdir()
    inputs.mkdir()
    reloads = []

    async def reload_func(working_dir, workspace):
        reloads.append((working_dir, workspace))

    monkeypatch.setattr(workspace_routes, "_root_working_dir", str(working))
    monkeypatch.setattr(workspace_routes, "_root_input_dir", str(inputs))
    monkeypatch.setattr(workspace_routes, "_reload_rag_func", reload_func)
    monkeypatch.setattr(workspace_routes, "_rag_instance", SimpleNamespace(workspace="w0"))
    monkeypatch.setattr(workspace_routes, "_current_workspace", None)

    async def idle(name, workspace=""):
        return {"busy": False}

    monkeypatch.setattr("lightrag.kg.shared_storage.get_namespace_data", idle)

    app = FastAPI()
    app.include_router(workspace_routes.create_workspace_routes("test-key"))
    return SimpleNamespace(
        client=TestClient(app), working=working, inputs=inputs, reloads=reloads
    )


def _body(env, name="sea_cabin", working=None, inputs=None):
    return {
        "name": name,
        "working_dir": str(working or env.working),
        "input_dir": str(inputs or env.inputs / name),
    }


def test_endpoints_require_authentication(env):
    for method, path in [
        ("get", "/workspace/current"),
        ("get", "/workspace/list"),
    ]:
        assert getattr(env.client, method)(path).status_code in (401, 403)
    assert env.client.post("/workspace/switch", json=_body(env)).status_code in (401, 403)
    assert env.client.post("/workspace/create", json=_body(env)).status_code in (401, 403)
    assert env.reloads == []


def test_switch_reloads_and_records_the_workspace(env):
    response = env.client.post("/workspace/switch", json=_body(env), headers=HEADERS)
    assert response.status_code == 200
    assert env.reloads == [(str(env.working), "sea_cabin")]
    assert env.client.get("/workspace/current", headers=HEADERS).json()["name"] == "sea_cabin"


def test_a_failed_reload_does_not_change_the_reported_workspace(env, monkeypatch):
    async def broken(working_dir, workspace):
        raise RuntimeError("storage down")

    monkeypatch.setattr(workspace_routes, "_reload_rag_func", broken)
    response = env.client.post("/workspace/switch", json=_body(env), headers=HEADERS)
    assert response.status_code == 500
    assert env.client.get("/workspace/current", headers=HEADERS).json()["name"] == "w0"


@pytest.mark.parametrize("name", ["../escape", "a/b", "x y", "", "a" * 65, "x;y"])
def test_workspace_names_are_restricted(env, name):
    response = env.client.post(
        "/workspace/switch", json=_body(env, name=name or "x"), headers=HEADERS
    ) if name else env.client.post(
        "/workspace/switch", json={**_body(env), "name": ""}, headers=HEADERS
    )
    assert response.status_code == 422
    assert env.reloads == []


def test_directories_outside_the_roots_are_refused_not_created(env, tmp_path):
    outside = tmp_path / "elsewhere"
    response = env.client.post(
        "/workspace/switch", json=_body(env, working=outside), headers=HEADERS
    )
    assert response.status_code == 400
    assert not outside.exists()

    response = env.client.post(
        "/workspace/create", json=_body(env, inputs=tmp_path / "other_inputs"), headers=HEADERS
    )
    assert response.status_code == 400
    assert not (tmp_path / "other_inputs").exists()


def test_switch_is_refused_while_the_pipeline_is_busy(env, monkeypatch):
    async def busy(name, workspace=""):
        return {"busy": True}

    monkeypatch.setattr("lightrag.kg.shared_storage.get_namespace_data", busy)
    response = env.client.post("/workspace/switch", json=_body(env), headers=HEADERS)
    assert response.status_code == 409
    assert env.reloads == []


def test_create_makes_directories_under_the_roots(env):
    response = env.client.post("/workspace/create", json=_body(env), headers=HEADERS)
    assert response.status_code == 200
    assert (env.inputs / "sea_cabin").is_dir()


@pytest.fixture
def workspace_specific_input_dir(env, monkeypatch):
    """INPUT_DIR=inputs/${WORKSPACE}, the convention in this fork's .env."""
    monkeypatch.setenv("WORKSPACE", "w0")
    monkeypatch.setattr(workspace_routes, "_root_input_dir", str(env.inputs / "w0"))
    for name in ("w0", "las_cabin"):
        (env.working / name).mkdir()
        (env.inputs / name).mkdir()
    return env


def test_listed_workspaces_can_be_switched_to_with_workspace_specific_input_dir(
    workspace_specific_input_dir,
):
    env = workspace_specific_input_dir
    listed = env.client.get("/workspace/list", headers=HEADERS).json()
    target = next(w for w in listed if w["name"] == "las_cabin")

    response = env.client.post("/workspace/switch", json=target, headers=HEADERS)

    assert response.status_code == 200, response.text
    assert env.reloads == [(target["working_dir"], "las_cabin")]


def test_workspace_specific_input_dir_still_refuses_dirs_outside_inputs(
    workspace_specific_input_dir, tmp_path
):
    env = workspace_specific_input_dir
    response = env.client.post(
        "/workspace/switch",
        json=_body(env, name="las_cabin", inputs=tmp_path / "elsewhere" / "las_cabin"),
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert env.reloads == []
