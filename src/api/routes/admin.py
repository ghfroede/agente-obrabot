"""Painel admin — monta auth + views e reexporta símbolos usados em testes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from src.api.routes import admin_auth, admin_views
from src.api.routes.admin_common import (
    check_same_origin as _check_same_origin,
)
from src.api.routes.admin_common import (
    effective_admin_password,
    require_admin_session,
)
from src.services import (
    admin_service,
    approval_service,
    entrada_service,
    obra_service,
    rate_limit_service,
    rdo_aggregator_service,
    rdo_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("", include_in_schema=False)
async def admin_root() -> RedirectResponse:
    return RedirectResponse("/admin/", status_code=307)


router.include_router(admin_auth.router)
router.include_router(admin_views.router)

__all__ = [
    "router",
    "_check_same_origin",
    "effective_admin_password",
    "require_admin_session",
    "admin_service",
    "approval_service",
    "entrada_service",
    "obra_service",
    "rate_limit_service",
    "rdo_aggregator_service",
    "rdo_service",
]
