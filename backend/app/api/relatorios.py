"""Relatórios e indicadores gerenciais (Nutrição / Admin)."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import Dieta, EntregaPedido, Pedido, RecebimentoEntrega, RecebimentoQR, Usuario
from ..services.relatorio_dietas import data_entrega
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
    horario_entrega = data_entrega()
    filtros = [Pedido.filial_id == filial_id, horario_entrega.is_not(None)]
    # Datas do filtro em Brasília (UTC-3); o banco armazena os horários em UTC.
    if data_inicio:
        filtros.append(horario_entrega >= datetime.combine(data_inicio, time.min) + timedelta(hours=3))
    if data_fim:
        filtros.append(horario_entrega < datetime.combine(data_fim, time.min) + timedelta(days=1, hours=3))
    base = select(Pedido).outerjoin(EntregaPedido, EntregaPedido.pedido_id == Pedido.id).outerjoin(RecebimentoQR, RecebimentoQR.pedido_id == Pedido.id).where(*filtros)
    total = await db.scalar(base.with_only_columns(func.count(), maintain_column_froms=True))
    linhas = (await db.execute(
        base.with_only_columns(Pedido, EntregaPedido, RecebimentoQR, RecebimentoEntrega.recebedor_nome, Usuario.nome, maintain_column_froms=True)
        .outerjoin(RecebimentoEntrega, RecebimentoEntrega.pedido_id == EntregaPedido.pedido_id)
        .outerjoin(Usuario, Usuario.id == EntregaPedido.registrado_por_usuario_id)
        .order_by(horario_entrega.desc(), Pedido.id.desc())
        .offset((pagina - 1) * 50).limit(50)
    )).all()
    itens = []
    for pedido, entrega, qr, recebedor, operador in linhas:
        dados = pedido.dados_dinamicos or {}
        retirada = pedido.retirada
        itens.append({"pedido_id": pedido.id, "tipo_solicitacao": pedido.tipo_solicitacao,
            "destinatario": pedido.nome_paciente or pedido.solicitante_nome,
            "solicitante_nome": pedido.solicitante_nome, "solicitante_identificacao": pedido.solicitante_identificacao,
            "leito": pedido.leito, "refeicao": dados.get("refeicao"),
            "local_entrega": dados.get("local_entrega") or dados.get("andar"),
            "copeira_nome": entrega.copeira_nome if entrega else retirada.copeira_nome if retirada else None,
            "copeira_id": entrega.copeira_id if entrega else retirada.copeira_id if retirada else None,
            "retirada_em": data_utc(retirada.retirada_em) if retirada else None,
            "recebedor_nome": qr.recebedor_nome if qr and qr.confirmado_em else recebedor, "registrado_por_nome": operador,
            "recebedor_registro_profissional": qr.registro_profissional if qr and qr.confirmado_em else None,
            "origem_entrega": 'QR Code' if qr and qr.confirmado_em else 'Copeira',
            "entregue_em": data_utc(qr.confirmado_em if qr and qr.confirmado_em else entrega.entregue_em), "assinatura_disponivel": recebedor is not None})
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
        criado = p.criado_em
        if criado and criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)
        hora = criado.astimezone(timezone(timedelta(hours=-3))).hour if criado else 0
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
