from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..core.security import exigir_perfis
from ..models.models import Usuario
from ..services.monitoramento import EstadoMonitoramento, obter_monitoramento, sondar_banco

router = APIRouter(prefix="/api", tags=["Monitoramento"])


@router.get("/health/ready")
async def prontidao(db: AsyncSession = Depends(get_db)):
    disponivel = (await sondar_banco(db))["estado"] == "CONECTADO"
    return JSONResponse({"status": "ok" if disponivel else "indisponivel"}, status_code=200 if disponivel else 503,
        headers={"Cache-Control": "no-store"})


@router.get("/admin/monitoramento")
async def monitorar(request: Request, response: Response, db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    response.headers["Cache-Control"] = "private, no-store"
    estado = getattr(request.app.state, "monitoramento", None) or EstadoMonitoramento()
    return await obter_monitoramento(db, estado, settings.BACKUP_RELATORIO_ARQUIVO)
