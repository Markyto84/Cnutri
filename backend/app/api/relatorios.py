"""Relatórios e indicadores gerenciais (Nutrição / Admin)."""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import Dieta, EntregaPedido, Pedido, RecebimentoEntrega, Usuario
from ..schemas.schemas import RelatorioConsumoItem, RelatorioDietasItem, RelatorioSLAOut
from ..services.operacao import data_utc

router = APIRouter(prefix="/api/relatorios", tags=["Relatórios"])
PERFIS = ("NUTRICIONISTA", "ADMIN_TI")


@router.get("/entregas")
async def relatorio_entregas(
    filial_id: int, data_inicio: date | None = None, data_fim: date | None = None,
    pagina: int = Query(default=1, ge=1), db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis(*PERFIS)),
):
    await verificar_acesso_filial(filial_id, usuario, db)
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(422, "A data inicial deve ser anterior ou igual à data final")
    filtros = [Pedido.filial_id == filial_id]
    # Datas do filtro em Brasília (UTC-3); o banco armazena os horários em UTC.
    if data_inicio:
        filtros.append(EntregaPedido.entregue_em >= datetime.combine(data_inicio, time.min) + timedelta(hours=3))
    if data_fim:
        filtros.append(EntregaPedido.entregue_em < datetime.combine(data_fim, time.min) + timedelta(days=1, hours=3))
    total = await db.scalar(select(func.count()).select_from(EntregaPedido).join(Pedido).where(*filtros))
    linhas = (await db.execute(
        select(EntregaPedido, Pedido, RecebimentoEntrega.recebedor_nome, Usuario.nome)
        .join(Pedido, Pedido.id == EntregaPedido.pedido_id)
        .outerjoin(RecebimentoEntrega, RecebimentoEntrega.pedido_id == EntregaPedido.pedido_id)
        .outerjoin(Usuario, Usuario.id == EntregaPedido.registrado_por_usuario_id)
        .where(*filtros).order_by(EntregaPedido.entregue_em.desc(), EntregaPedido.pedido_id.desc())
        .offset((pagina - 1) * 50).limit(50)
    )).all()
    itens = []
    for entrega, pedido, recebedor, operador in linhas:
        dados = pedido.dados_dinamicos or {}
        itens.append({"pedido_id": pedido.id, "tipo_solicitacao": pedido.tipo_solicitacao,
            "destinatario": pedido.nome_paciente or pedido.solicitante_nome,
            "leito": pedido.leito, "refeicao": dados.get("refeicao"),
            "local_entrega": dados.get("local_entrega") or dados.get("andar"),
            "copeira_nome": entrega.copeira_nome, "recebedor_nome": recebedor, "registrado_por_nome": operador,
            "entregue_em": data_utc(entrega.entregue_em), "assinatura_disponivel": recebedor is not None})
    return {"itens": itens, "total": total, "pagina": pagina, "total_paginas": max(1, ((total or 0) + 49) // 50)}


@router.get("/entregas/{pedido_id}/assinatura")
async def assinatura_entrega(pedido_id: int, filial_id: int, db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis(*PERFIS))):
    await verificar_acesso_filial(filial_id, usuario, db)
    imagem = await db.scalar(select(RecebimentoEntrega.assinatura_png)
        .join(EntregaPedido, EntregaPedido.pedido_id == RecebimentoEntrega.pedido_id)
        .join(Pedido, Pedido.id == EntregaPedido.pedido_id)
        .where(Pedido.id == pedido_id, Pedido.filial_id == filial_id))
    if imagem is None:
        raise HTTPException(404, "Assinatura não encontrada para este pedido nesta unidade")
    return Response(content=imagem, media_type="image/png", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="assinatura-pedido-{pedido_id}.png"',
    })


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
            .where(Pedido.filial_id == filial_id, Pedido.tipo_solicitacao == "MEDICO", Pedido.status.in_(("PRONTO", "ENTREGUE")))
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
