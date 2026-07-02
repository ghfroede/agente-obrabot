from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from src.core.errors import BucketConflictError
from src.services import bucket_service


@pytest.fixture
def local_bucket_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    settings = SimpleNamespace(
        s3_endpoint_url="",
        s3_access_key_id="",
        s3_secret_access_key="",
        local_bucket_path=str(tmp_path),
        s3_bucket_name="test-bucket",
        s3_configured=False,
    )
    monkeypatch.setattr(bucket_service, "get_settings", lambda: settings)


def test_obra_storage_prefix_with_slug() -> None:
    assert bucket_service.obra_storage_prefix("OBRA-1", "obra-alpha") == "obras/OBRA-1-obra-alpha"


def test_build_entrada_bruta_key_uses_entrada_id() -> None:
    key = bucket_service.build_entrada_bruta_key(
        "OBRA-1",
        "evt-1",
        slug="obra",
        source="telegram",
        data_ref=date(2026, 6, 27),
        entrada_id="ent-99",
    )
    assert key.endswith("/envelope.json")
    assert "entrada_ent-99" in key
    assert "/2026/06/27/" in key


def test_build_rdo_key_draft_vs_final() -> None:
    draft = bucket_service.build_rdo_key("OBRA-1", "2026-06-27", "REV00", "rdo.pdf", draft=True)
    final = bucket_service.build_rdo_key("OBRA-1", "2026-06-27", "REV00", "rdo.pdf", draft=False)
    assert "rascunhos" in draft
    assert "finalizados_pdf" in final


def test_build_metadata_key() -> None:
    assert (
        bucket_service.build_metadata_key("obras/O1/05_RDO/rascunhos/2026-06-27/REV00/rdo.pdf")
        == "obras/O1/05_RDO/rascunhos/2026-06-27/REV00/rdo.metadata.json"
    )


def test_put_and_get_bytes_local(local_bucket_settings: None, tmp_path: object) -> None:
    uri = bucket_service.put_bytes("path/file.bin", b"hello", content_type="text/plain")
    assert uri.startswith("s3://test-bucket/")
    assert bucket_service.get_bytes("path/file.bin") == b"hello"
    assert bucket_service.head_object("path/file.bin") is True
    assert bucket_service.head_object("missing.bin") is False


def test_put_bytes_conflict_when_not_allowed(local_bucket_settings: None) -> None:
    bucket_service.put_bytes("dup.bin", b"v1")
    with pytest.raises(BucketConflictError):
        bucket_service.put_bytes("dup.bin", b"v2", allow_overwrite=False)


def test_persist_entrada_bruta_adds_schema_and_hash(local_bucket_settings: None) -> None:
    key, uri = bucket_service.persist_entrada_bruta(
        obra_id="OBRA-1",
        event_id="evt-1",
        envelope={"text": "oi"},
        slug="obra",
        entrada_id="ent-1",
        data_ref=date(2026, 6, 27),
    )
    raw = bucket_service.get_bytes(key)
    payload = json.loads(raw.decode("utf-8"))
    assert payload["schema_version"]
    assert payload["generated_by"]
    assert payload["hash_sha256"]
    assert payload["text"] == "oi"
    assert uri.endswith(key)
