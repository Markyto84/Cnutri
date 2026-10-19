"""Relatórios e indicadores gerenciais (Nutrição / Admin)."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import Dieta, Pedido, Usuario
from ..schemas.schemas import RelatorioConsumoItem, RelatorioDietasItem, RelatorioSLAOut

router = APIRouter(prefix="/api/relatorios", tags=["Relatórios"])
PERFIS = ("NUTRICIONISTA", "ADMIN_TI")


@router.get("/sla", response_model=RelatorioSLAOut)
async def sla_medico(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS))):
    """Tempo médio entre envio do pedido e conclusão na cozinha."""
    await verificar_acesso_filial(filial_id, _, db)
    resultado = await db.execute(
        select(
            func.count(Pedido.id),
            func.avg(
                func.extract("epoch", Pedido.concluido_em - Pedido.criado_em) / 60.0
            ),
        ).where(Pedido.filial_id == filial_id, Pedido.concluido_em.is_not(None))
    )
    total, media = resultado.one()
    return RelatorioSLAOut(total_concluidos=total or 0, sla_medio_minutos=round(media, 1) if media else None)


@router.get("/consumo-medico", response_model=list[RelatorioConsumoItem])
async def consumo_medico(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS))):
    """Refeições servidas ao corpo médico, agrupadas por turno e profissional."""
    await verificar_acesso_filial(filial_id, _, db)
    pedidos = (
        await db.execute(
            select(Pedido)
            .where(Pedido.filial_id == filial_id, Pedido.tipo_solicitacao == "MEDICO", Pedido.status == "PRONTO")
        )
    ).scalars().all()

    contagem: dict[tuple[str, str], int] = {}
    for p in pedidos:
        hora = p.criado_em.hour if p.criado_em else 0
        turno = "Manhã" if 6 <= hora < 12 else "Tarde" if 12 <= hora < 18 else "Noite"
        chave = (turno, p.solicitante_nome or p.solicitante_identificacao)
        contagem[chave] = contagem.get(chave, 0) + 1
    return [
        RelatorioConsumoItem(turno=t, solicitante=s, total=n)
        for (t, s), n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0][0]))
    ]


@router.get("/dietas", response_model=list[RelatorioDietasItem])
async def estatisticas_dietas(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS))):
    """Volume de pedidos por tipo de dieta."""
    await verificar_acesso_filial(filial_id, _, db)
    linhas = (
        await db.execute(
            select(Dieta.nome, func.count(Pedido.id))
            .join(Pedido, Pedido.dieta_id == Dieta.id)
            .where(Pedido.filial_id == filial_id)
            .group_by(Dieta.nome)
            .order_by(func.count(Pedido.id).desc())
        )
    ).all()
    return [RelatorioDietasItem(dieta=nome, total=total) for nome, total in linhas]
