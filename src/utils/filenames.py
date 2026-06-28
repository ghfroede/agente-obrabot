import re

from slugify import slugify

from src.core.constants import DocumentStatus


def obra_slug(nome: str) -> str:
    return slugify(nome, separator="-")[:80] or "obra"


def next_revision(existing: list[str]) -> str:
    nums = []
    for rev in existing:
        match = re.search(r"REV(\d+)", rev)
        if match:
            nums.append(int(match.group(1)))
    n = max(nums, default=-1) + 1
    return f"REV{n:02d}"


def build_document_filename(
    *,
    tipo: str,
    obra_id: str,
    data_ref: str,
    revisao: str,
    status: DocumentStatus | str,
    ext: str = "pdf",
) -> str:
    status_part = str(status).split(".")[-1] if "." in str(status) else str(status)
    if status_part in ("FINALIZADO_VALIDADO", "APROVADO", "PUBLICADO_BUCKET"):
        status_part = "FINAL"
    elif status_part in ("RASCUNHO_GERADO", "EM_REVISAO"):
        status_part = "DRAFT"
    return f"{tipo}_{obra_id}_{data_ref}_{revisao}_{status_part}.{ext}"


def build_photo_report_filename(
    obra_id: str,
    periodo_inicio: str,
    periodo_fim: str,
    revisao: str,
    final: bool = True,
) -> str:
    suffix = "FINAL" if final else "DRAFT"
    return (
        f"RELATORIO_FOTOGRAFICO_{obra_id}_{periodo_inicio}_a_{periodo_fim}_{revisao}_{suffix}.pdf"
    )
