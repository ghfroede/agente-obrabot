from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.deps import get_db
from src.api.routes import admin as admin_route
from src.api.server import create_app
from src.config.env import get_settings
from src.core.constants import DocumentStatus


@pytest.fixture(autouse=True)
def clear_settings_cache() -> AsyncIterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _build_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")
    monkeypatch.setenv("SESSION_SECRET", "session-secret-xyz")
    monkeypatch.setattr(admin_route.rate_limit_service, "check_admin_login_limit", lambda **_: None)
    app = create_app()

    async def _fake_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return app


async def _login(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/admin/login", data={"senha": "segredo123"}, follow_redirects=False
    )
    assert resp.status_code == 303


def _client(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_criar_obra_calls_upsert_and_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    upsert = AsyncMock(return_value=SimpleNamespace(id="OBRA-1"))
    monkeypatch.setattr(admin_route.obra_service, "upsert_obra", upsert)

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            "/admin/obras/nova",
            data={"id": "obra-1", "nome": "Obra Um", "status": "ativa"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    upsert.assert_awaited_once()


async def test_toggle_status_calls_set_status_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    obra_ativa = SimpleNamespace(id="OBRA-1", nome="Obra Um", status="ativa")
    obra_inativa = SimpleNamespace(id="OBRA-1", nome="Obra Um", status="inativa")
    # Toggle agora resolve a obra com um único session.get (sem list_obras).
    fake_session = AsyncMock()
    fake_session.get = AsyncMock(return_value=obra_ativa)

    async def _fake_db() -> AsyncIterator[AsyncMock]:
        yield fake_session

    app.dependency_overrides[get_db] = _fake_db
    set_status = AsyncMock(return_value=obra_inativa)
    monkeypatch.setattr(admin_route.obra_service, "set_status", set_status)

    async with _client(app) as client:
        await _login(client)
        resp = await client.post("/admin/obras/OBRA-1/status")

    assert resp.status_code == 200
    set_status.assert_awaited_once_with(set_status.await_args.args[0], "OBRA-1", "inativa")
    assert "inativa" in resp.text


async def test_resolver_obra_success(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    resolve = AsyncMock(return_value={"status": "queued", "obra_id": "OBRA-1"})
    monkeypatch.setattr(admin_route.entrada_service, "resolve_pending_obra", resolve)
    # Garante que enqueue (Redis) não é chamado de verdade.
    monkeypatch.setattr(admin_route.entrada_service, "enqueue_entrada", lambda *_: None)
    eid = uuid.uuid4()

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            f"/admin/entradas/{eid}/resolver-obra", data={"obra_id": "OBRA-1"}
        )

    assert resp.status_code == 200
    resolve.assert_awaited_once()
    assert "OBRA-1" in resp.text


async def test_resolver_obra_translates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    monkeypatch.setattr(admin_route.entrada_service, "enqueue_entrada", lambda *_: None)
    eid = uuid.uuid4()

    for status, esperado in [
        ({"status": "not_found"}, "não encontrada"),
        ({"status": "obra_not_found"}, "não encontrada"),
    ]:
        monkeypatch.setattr(
            admin_route.entrada_service,
            "resolve_pending_obra",
            AsyncMock(return_value=status),
        )
        async with _client(app) as client:
            await _login(client)
            resp = await client.post(
                f"/admin/entradas/{eid}/resolver-obra", data={"obra_id": "X"}
            )
        assert resp.status_code == 200
        assert esperado in resp.text


async def test_dia_obra_renders_aggregated_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    obra = SimpleNamespace(id="OBRA-1", nome="Obra Um", status="ativa")
    conteudo = {
        "obra": {"id": "OBRA-1", "nome": "Obra Um"},
        "data_ref": "2026-06-29",
        "source_entrada_ids": [str(uuid.uuid4())],
        "source_arquivo_ids": [str(uuid.uuid4())],
        "resumo_operacional": {
            "entradas_count": 1,
            "triagens_count": 1,
            "fotos_count": 1,
            "audios_count": 0,
            "arquivos_count": 1,
        },
        "servicos": [
            {
                "entrada_id": str(uuid.uuid4()),
                "source": "openclaw",
                "status": "completed",
                "author": "Engenharia",
                "created_at": "2026-06-29T10:00:00+00:00",
                "text": "Equipe elétrica executou infraestrutura.",
                "storage_uri": "s3://bucket/raw.json",
                "triagens": [
                    {
                        "triagem_id": str(uuid.uuid4()),
                        "documento_id": None,
                        "tipo_documento": "rdo_evento",
                        "confianca": 0.92,
                        "resumo": "Infraestrutura elétrica em execução.",
                        "created_at": "2026-06-29T10:01:00+00:00",
                        "campos_extraidos": {},
                        "acao_sugerida": None,
                        "precisa_aprovacao": True,
                    }
                ],
            }
        ],
        "pendencias": ["Confirmar equipe terceirizada."],
        "fotos": [
            {
                "foto_id": str(uuid.uuid4()),
                "arquivo_id": str(uuid.uuid4()),
                "entrada_id": str(uuid.uuid4()),
                "data_foto": "2026-06-29",
                "created_at": "2026-06-29T10:02:00+00:00",
                "descricao": "Painel instalado.",
                "bucket_uri": "s3://bucket/foto.jpg",
            }
        ],
        "audios": [],
        "documentos_brutos": [],
    }
    monkeypatch.setattr(
        admin_route.obra_service, "list_obras", AsyncMock(return_value=[obra])
    )
    aggregate = AsyncMock(return_value=conteudo)
    monkeypatch.setattr(
        admin_route.rdo_aggregator_service, "aggregate_daily_rdo", aggregate
    )

    async with _client(app) as client:
        await _login(client)
        resp = await client.get(
            "/admin/dia-obra?obra_id=OBRA-1&data_ref=2026-06-29"
        )

    assert resp.status_code == 200
    aggregate.assert_awaited_once()
    assert "Equipe elétrica executou infraestrutura." in resp.text
    assert "Confirmar equipe terceirizada." in resp.text


async def test_dia_obra_gerar_rdo_redirects_to_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    obra = SimpleNamespace(id="OBRA-1", nome="Obra Um", status="ativa")
    conteudo = {
        "obra": {"id": "OBRA-1", "nome": "Obra Um"},
        "data_ref": "2026-06-29",
        "source_entrada_ids": [],
        "source_arquivo_ids": [],
    }
    documento_id = uuid.uuid4()
    monkeypatch.setattr(
        admin_route.obra_service, "list_obras", AsyncMock(return_value=[obra])
    )
    aggregate = AsyncMock(return_value=conteudo)
    create_draft = AsyncMock(
        return_value={
            "documento_id": str(documento_id),
            "status": "RASCUNHO_GERADO",
            "revisao": "R0",
            "bucket_uri": "s3://bucket/rdo.html",
        }
    )
    monkeypatch.setattr(
        admin_route.rdo_aggregator_service, "aggregate_daily_rdo", aggregate
    )
    monkeypatch.setattr(admin_route.rdo_service, "create_rdo_draft", create_draft)

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            "/admin/dia-obra/gerar-rdo",
            data={"obra_id": "OBRA-1", "data_ref": "2026-06-29"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/documentos/{documento_id}"
    aggregate.assert_awaited_once()
    create_draft.assert_awaited_once()


async def test_documento_detail_renders_rdo_edit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    doc = SimpleNamespace(
        id=uuid.uuid4(),
        tipo="rdo",
        titulo="RDO OBRA-1",
        status=DocumentStatus.RASCUNHO_GERADO,
        obra_id="OBRA-1",
        revisao="REV00",
        metadata_json={
            "campos_editaveis": {
                "clima": "Sol",
                "equipe": ["Mestre João", "2 pedreiros"],
                "equipamentos": [],
                "observacoes": ["Sem interferências."],
                "complementos_engenheiro": [],
            }
        },
    )
    monkeypatch.setattr(
        admin_route.admin_service,
        "get_documento_com_triagem",
        AsyncMock(return_value=(doc, None)),
    )

    async with _client(app) as client:
        await _login(client)
        resp = await client.get(f"/admin/documentos/{doc.id}")

    assert resp.status_code == 200
    assert "Complementos do RDO" in resp.text
    assert "Sol" in resp.text
    assert "Mestre João" in resp.text


async def test_documento_rdo_campos_submit_updates_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    update = AsyncMock(
        return_value={
            "documento_id": "doc-1",
            "status": "EM_REVISAO",
            "bucket_uri": "s3://bucket/rdo.html",
        }
    )
    monkeypatch.setattr(admin_route.rdo_service, "update_rdo_draft_fields", update)
    did = uuid.uuid4()

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            f"/admin/documentos/{did}/rdo-campos",
            data={
                "editor": "engenheiro",
                "clima": "Sol",
                "equipe": "Mestre João\n2 pedreiros",
                "equipamentos": "Betoneira",
                "observacoes": "Sem interferências.",
                "complementos_engenheiro": "Liberar frente amanhã.",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/documentos/{did}?rdo_campos=ok"
    update.assert_awaited_once()
    assert update.await_args.kwargs["documento_id"] == str(did)
    assert update.await_args.kwargs["campos"]["equipe"] == "Mestre João\n2 pedreiros"


async def test_documento_detail_renders_rdo_finalize_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    doc = SimpleNamespace(
        id=uuid.uuid4(),
        tipo="rdo",
        titulo="RDO OBRA-1",
        status=DocumentStatus.APROVADO,
        obra_id="OBRA-1",
        revisao="REV00",
        data_ref=None,
        bucket_uri="s3://bucket/rdo.html",
        hash_sha256="h" * 64,
        metadata_json={},
    )
    monkeypatch.setattr(
        admin_route.admin_service,
        "get_documento_com_triagem",
        AsyncMock(return_value=(doc, None)),
    )

    async with _client(app) as client:
        await _login(client)
        resp = await client.get(f"/admin/documentos/{doc.id}")

    assert resp.status_code == 200
    assert "Finalizar RDO PDF" in resp.text
    assert "s3://bucket/rdo.html" in resp.text


async def test_documento_finalizar_rdo_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    finalize = AsyncMock(
        return_value={
            "documento_id": "doc-1",
            "status": "FINALIZADO_VALIDADO",
            "bucket_uri": "s3://bucket/rdo.pdf",
            "formato": "pdf",
        }
    )
    monkeypatch.setattr(admin_route.rdo_service, "finalize_rdo", finalize)
    did = uuid.uuid4()

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            f"/admin/documentos/{did}/finalizar-rdo",
            data={"aprovador": "engenheiro"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/admin/documentos/{did}?rdo_finalizado=ok"
    finalize.assert_awaited_once_with(
        finalize.await_args.args[0],
        documento_id=str(did),
        aprovador="engenheiro",
    )


async def test_aprovar_documento_aprovado(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    approve = AsyncMock(
        return_value={"documento_id": "d1", "status": "APROVADO", "aprovado": True}
    )
    monkeypatch.setattr(admin_route.approval_service, "approve_document", approve)
    did = uuid.uuid4()

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            f"/admin/documentos/{did}/aprovar",
            data={"aprovado": "true", "aprovador": "eng"},
        )

    assert resp.status_code == 200
    assert approve.await_args.kwargs["aprovado"] is True
    assert "APROVADO" in resp.text


async def test_aprovar_documento_reprovado(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    approve = AsyncMock(
        return_value={"documento_id": "d1", "status": "REPROVADO", "aprovado": False}
    )
    monkeypatch.setattr(admin_route.approval_service, "approve_document", approve)
    did = uuid.uuid4()

    async with _client(app) as client:
        await _login(client)
        resp = await client.post(
            f"/admin/documentos/{did}/aprovar",
            data={"aprovado": "false", "aprovador": "eng"},
        )

    assert resp.status_code == 200
    assert approve.await_args.kwargs["aprovado"] is False
    assert "REPROVADO" in resp.text


async def test_entrada_detail_escapes_xss(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    entrada = SimpleNamespace(
        id=uuid.uuid4(),
        source="telegram",
        status="received",
        obra_id="OBRA-1",
        author="<script>alert('xss')</script>",
        created_at=None,
        text="ok",
        raw_payload={"evil": "<script>alert('x')</script>"},
    )
    monkeypatch.setattr(
        admin_route.admin_service, "get_entrada", AsyncMock(return_value=entrada)
    )
    monkeypatch.setattr(
        admin_route.obra_service, "active_obras_summary", AsyncMock(return_value=[])
    )

    async with _client(app) as client:
        await _login(client)
        resp = await client.get(f"/admin/entradas/{entrada.id}")

    assert resp.status_code == 200
    assert "<script>alert" not in resp.text
    assert "&lt;script&gt;" in resp.text


async def test_entradas_filter_valid_status(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    entrada = SimpleNamespace(
        id=uuid.uuid4(),
        source="telegram",
        status="pending_obra",
        obra_id=None,
        author="a",
        created_at=None,
    )
    list_mock = AsyncMock(return_value=[entrada])
    monkeypatch.setattr(admin_route.admin_service, "list_entradas", list_mock)

    async with _client(app) as client:
        await _login(client)
        resp = await client.get("/admin/entradas?status=pending_obra")

    assert resp.status_code == 200
    assert list_mock.await_args.kwargs["status"] == "pending_obra"


async def test_entradas_invalid_status_no_500(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    list_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(admin_route.admin_service, "list_entradas", list_mock)

    async with _client(app) as client:
        await _login(client)
        resp = await client.get("/admin/entradas?status=queued")

    assert resp.status_code == 200
    # "queued" não é status válido de EntradaBruta — vira filtro None.
    assert list_mock.await_args.kwargs["status"] is None


async def test_documentos_filter_valid_status(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    doc = SimpleNamespace(
        id=uuid.uuid4(),
        tipo="rdo",
        titulo="RDO",
        status=DocumentStatus.EM_REVISAO,
        obra_id="OBRA-1",
        created_at=None,
    )
    list_mock = AsyncMock(return_value=[doc])
    monkeypatch.setattr(admin_route.admin_service, "list_documentos", list_mock)

    async with _client(app) as client:
        await _login(client)
        resp = await client.get("/admin/documentos?status=EM_REVISAO")

    assert resp.status_code == 200
    assert list_mock.await_args.kwargs["status"] == "EM_REVISAO"


async def test_documentos_invalid_status_no_500(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    list_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(admin_route.admin_service, "list_documentos", list_mock)

    async with _client(app) as client:
        await _login(client)
        resp = await client.get("/admin/documentos?status=naoexiste")

    assert resp.status_code == 200
    assert list_mock.await_args.kwargs["status"] is None
