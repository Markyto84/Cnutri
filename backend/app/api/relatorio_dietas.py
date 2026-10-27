"""Relatório completo e exportações restritos à Gestão e Administração."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, filiais_permitidas, verificar_acesso_filial
from ..models.models import EntregaPedido, Pedido, Usuario
from ..services.relatorio_dietas import BRASILIA, STATUS, TIPOS, ConsultaDietas, agrupar, consulta_base, detalhar, resumir, data_entrega
from ..services.exportacao_dietas import exportar_dietas

router = APIRouter(prefix="/api/relatorios/dietas-periodo", tags=["Relatórios de dietas"])


async def preparar_consulta(
    inicio: datetime, fim: datetime, filial_id: int | None = Query(default=None, gt=0),
    data_base: Literal["solicitacao", "entrega"] = "solicitacao",
    tipo_solicitacao: Literal["PACIENTE", "MEDICO"] | None = None,
    status: Literal["PENDENTE", "EM_PREPARO", "PRONTO", "ENTREGUE", "CANCELADO"] | None = None,
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(exigir_perfis("ADMIN_TI", "NUTRICIONISTA")),
):
    try:
        inicio = inicio.replace(tzinfo=BRASILIA) if inicio.tzinfo is None else inicio
        fim = fim.replace(tzinfo=BRASILIA) if fim.tzinfo is None else fim
        inicio_utc = inicio.astimezone(timezone.utc).replace(tzinfo=None)
        fim_utc = fim.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Informe um período de datas válido")
    if inicio_utc > fim_utc:
        raise HTTPException(422, "A data e hora inicial devem ser anteriores ou iguais às finais")
    if filial_id is not None:
        filiais = [await verificar_acesso_filial(filial_id, usuario, db)]
    else:
        filiais = await filiais_permitidas(usuario, db)
    data = data_entrega() if data_base == "entrega" else Pedido.criado_em
    filtros = [Pedido.filial_id.in_([f.id for f in filiais]), data >= inicio_utc, data <= fim_utc]
    if tipo_solicitacao:
        filtros.append(Pedido.tipo_solicitacao == tipo_solicitacao)
    if status:
        filtros.append(Pedido.status == status)
    return ConsultaDietas(filtros, {"inicio": inicio.astimezone(BRASILIA).isoformat(), "fim": fim.astimezone(BRASILIA).isoformat(),
        "data_base": data_base, "unidades": [f"{f.nome} ({f.codigo_slug})" for f in filiais],
        "tipo": TIPOS.get(tipo_solicitacao, "Todos"), "status": STATUS.get(status, "Todos")})


@router.get("")
async def visualizar(consulta: ConsultaDietas = Depends(preparar_consulta), pagina: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db)):
    resumo, totais = await resumir(db, consulta)
    linhas = (await db.execute(consulta_base(consulta).order_by(Pedido.criado_em.desc(), Pedido.id.desc())
        .offset((pagina - 1) * 25).limit(25))).all()
    return {"contexto": consulta.contexto, "resumo": resumo, "totais": totais, "itens": [detalhar(linha) for linha in linhas],
        "pagina": pagina, "total_paginas": max(1, (totais["total"] + 24) // 25)}


@router.get("/exportar")
async def exportar(formato: Literal["xlsx", "ods", "csv"], consulta: ConsultaDietas = Depends(preparar_consulta),
    db: AsyncSession = Depends(get_db)):
    linhas = (await db.execute(consulta_base(consulta).order_by(Pedido.criado_em, Pedido.id))).all()
    itens = [detalhar(linha) for linha in linhas]
    resumo, totais = agrupar((item["unidade_id"], item["unidade_codigo"], item["unidade"], item["dieta_id"], item["dieta"], item["status"], 1) for item in itens)
    try:
        arquivo, mime = await run_in_threadpool(exportar_dietas, formato, itens, resumo, totais, consulta.contexto)
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    periodo = datetime.fromisoformat(consulta.contexto["inicio"]).strftime("%Y%m%d-%H%M")
    fim = datetime.fromisoformat(consulta.contexto["fim"]).strftime("%Y%m%d-%H%M")
    nome = f"cnutri-dietas-{periodo}-a-{fim}.{formato}"
    return Response(content=arquivo, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })
