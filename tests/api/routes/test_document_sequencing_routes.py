"""Sequencing routes: real doc_status API, one metadata key, safe uploads."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Importing the API package parses sys.argv; shield it from pytest's arguments.
_original_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
global_args = importlib.import_module("lightrag.api.config").global_args
create_sequencing_routes = importlib.import_module(
    "lightrag.api.routers.document_sequencing_routes"
).create_sequencing_routes
sys.argv = _original_argv

from lightrag.base import DeletionResult  # noqa: E402

pytestmark = pytest.mark.offline

HEADERS = {"X-API-Key": "test-key"}


class _FakeDocStatus:
    def __init__(self, rows):
        self.rows = rows
        self.updated = []

    async def get_by_id(self, doc_id):
        return self.rows.get(doc_id)

    async def update_doc_status_fields(self, doc_id, fields, *, missing_ok=False):
        self.rows[doc_id].update(fields)
        self.updated.append((doc_id, fields))

    async def get_docs_paginated(self, page=1, page_size=50, **_kwargs):
        items = [
            (
                doc_id,
                SimpleNamespace(
                    metadata=row.get("metadata"),
                    status=row.get("status"),
                    file_path=row.get("file_path"),
                ),
            )
            for doc_id, row in self.rows.items()
        ]
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)


class _FakeRag:
    def __init__(self, rows):
        self.doc_status = _FakeDocStatus(rows)
        self.deleted = []

    async def adelete_by_doc_id(self, doc_id, delete_llm_cache=False):
        self.deleted.append(doc_id)
        self.doc_status.rows.pop(doc_id, None)
        return DeletionResult(status="success", doc_id=doc_id, message="deleted")


def _client(rag):
    app = FastAPI()
    app.include_router(create_sequencing_routes(rag, api_key="test-key"))
    return TestClient(app)


def _rows():
    return {
        "doc-1": {
            "status": "processed",
            "file_path": "base.md",
            "metadata": {"sequence_index": 1, "effective_date": "2024-01-01", "doc_type": "base"},
        },
        "doc-2": {
            "status": "pending",
            "file_path": "amend.md",
            "metadata": {"sequence_index": 2, "date": "2024-06-01"},
        },
    }


def test_listing_uses_the_real_storage_and_reports_effective_date():
    client = _client(_FakeRag(_rows()))
    response = client.get("/documents/sequences", headers=HEADERS)
    assert response.status_code == 200
    docs = response.json()["documents"]
    assert [d["sequence_index"] for d in docs] == [1, 2]
    assert docs[0]["effective_date"] == "2024-01-01"
    assert docs[1]["effective_date"] == "2024-06-01"  # legacy "date" key still read


def test_date_and_type_can_be_edited_on_a_processed_document():
    rag = _FakeRag(_rows())
    response = _client(rag).patch(
        "/documents/doc-1/sequence",
        headers=HEADERS,
        json={
            "document_id": "doc-1",
            "sequence_index": 1,
            "effective_date": "2024-02-02",
            "doc_type": "amendment",
        },
    )
    assert response.status_code == 200
    metadata = rag.doc_status.rows["doc-1"]["metadata"]
    assert metadata["effective_date"] == "2024-02-02"
    assert metadata["doc_type"] == "amendment"
    assert "date" not in metadata


def test_a_processed_document_cannot_change_its_sequence_index():
    rag = _FakeRag(_rows())
    response = _client(rag).patch(
        "/documents/doc-1/sequence",
        headers=HEADERS,
        json={"document_id": "doc-1", "sequence_index": 9},
    )
    assert response.status_code == 409
    assert rag.doc_status.rows["doc-1"]["metadata"]["sequence_index"] == 1


def test_a_pending_document_can_move_to_a_free_index_but_not_a_used_one():
    rag = _FakeRag(_rows())
    client = _client(rag)
    taken = client.patch(
        "/documents/doc-2/sequence",
        headers=HEADERS,
        json={"document_id": "doc-2", "sequence_index": 1},
    )
    assert taken.status_code == 409
    free = client.patch(
        "/documents/doc-2/sequence",
        headers=HEADERS,
        json={"document_id": "doc-2", "sequence_index": 5},
    )
    assert free.status_code == 200
    assert rag.doc_status.rows["doc-2"]["metadata"]["sequence_index"] == 5


def test_a_malformed_date_is_rejected():
    response = _client(_FakeRag(_rows())).patch(
        "/documents/doc-1/sequence",
        headers=HEADERS,
        json={"document_id": "doc-1", "sequence_index": 1, "effective_date": "01/02/2024"},
    )
    assert response.status_code == 422


def test_unknown_document_is_404():
    response = _client(_FakeRag(_rows())).patch(
        "/documents/nope/sequence",
        headers=HEADERS,
        json={"document_id": "nope", "sequence_index": 3},
    )
    assert response.status_code == 404


def test_delete_goes_through_adelete_by_doc_id(tmp_path, monkeypatch):
    monkeypatch.setattr(global_args, "input_dir", str(tmp_path), raising=False)
    (tmp_path / "base.md").write_text("x")
    rag = _FakeRag(_rows())
    response = _client(rag).delete("/documents/doc-1/sequenced", headers=HEADERS)
    assert response.status_code == 200
    assert rag.deleted == ["doc-1"]
    body = response.json()
    assert body["sequence_index"] == 1 and body["effective_date"] == "2024-01-01"
    assert body["deleted_file"] is True and not (tmp_path / "base.md").exists()


@pytest.mark.parametrize("name", ["../evil.md", "/etc/evil.md", "a/b.md", "..\\evil.md"])
def test_batch_upload_rejects_path_components_in_filenames(tmp_path, monkeypatch, name):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    monkeypatch.setattr(global_args, "input_dir", str(inputs), raising=False)
    response = _client(_FakeRag(_rows())).post(
        "/documents/batch-upload-sequenced",
        headers=HEADERS,
        files=[("files", (name, b"content", "text/markdown"))],
        data={"order": f'["{name}"]'.replace("\\", "\\\\")},
    )
    assert response.status_code == 400
    assert list(tmp_path.rglob("evil.md")) == []


def test_batch_upload_never_overwrites_an_existing_file(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "base.md").write_text("original")
    monkeypatch.setattr(global_args, "input_dir", str(inputs), raising=False)
    response = _client(_FakeRag(_rows())).post(
        "/documents/batch-upload-sequenced",
        headers=HEADERS,
        files=[("files", ("base.md", b"replacement", "text/markdown"))],
        data={"order": '["base.md"]'},
    )
    assert response.status_code == 409
    assert (inputs / "base.md").read_text() == "original"
