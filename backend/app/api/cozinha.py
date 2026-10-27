"""Operação da cozinha da intranet, independente de credenciais pessoais."""
from hashlib import sha256

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import operacao
from ..core.database import get_db
from ..models.models import Pedido
from ..schemas.schemas import ReimpressaoCreate, StatusUpdate
from ..services.contexto_operacao import carregar_contexto

router = APIRouter(prefix="/api/cozinha", tags=["Cozinha sem login"])


@router.get("/unidades/{filial_id}/estado")
async def estado(filial_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await operacao.unidade_ativa(filial_id, db)
    unidades, contexto = await carregar_contexto(db, {filial_id})
    pedidos = (await db.scalars(select(Pedido).options(selectinload(Pedido.dieta)).where(
        Pedido.filial_id == filial_id, Pedido.status.in_(operacao.STATUS_ATIVOS),
    ).order_by(Pedido.criado_em, Pedido.id))).all()
    # A cozinha recebe apenas o resumo operacional; prontuário, matrícula, prescrição
    # e histórico de recebimento permanecem fora do snapshot e do WebSocket.
    resposta = JSONResponse({"unidades": unidades, "alertas": contexto[filial_id]["alertas"],
        "pedidos": [operacao.serializar(p) for p in pedidos], "copeiras": []})
    etag = '"' + sha256(f"cozinha:{filial_id}:".encode() + resposta.body).hexdigest() + '"'
    cabecalhos = {"ETag": etag, "Cache-Control": "private, no-store"}
    if etag in [v.strip() for v in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=cabecalhos)
    resposta.headers.update(cabecalhos)
    return resposta


@router.patch("/unidades/{filial_id}/pedidos/{pedido_id}/status")
async def alterar_status(filial_id: int, pedido_id: int, dados: StatusUpdate, db: AsyncSession = Depends(get_db)):
    return await operacao.alterar_status(filial_id, pedido_id, dados, db, None)


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/reimprimir", status_code=202)
async def reimprimir(filial_id: int, pedido_id: int, dados: ReimpressaoCreate | None = None, db: AsyncSession = Depends(get_db)):
    return await operacao.reimprimir(filial_id, pedido_id, dados, db, None)


@router.get("/unidades/{filial_id}/pedidos/{pedido_id}/etiqueta")
async def previa_etiqueta(filial_id: int, pedido_id: int, indice: int = Query(0, ge=0, le=1), db: AsyncSession = Depends(get_db)):
    return await operacao.previa_etiqueta(filial_id, pedido_id, indice, db, None)


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/etiqueta", status_code=202)
async def imprimir_etiqueta(filial_id: int, pedido_id: int, dados: ReimpressaoCreate | None = None, db: AsyncSession = Depends(get_db)):
    return await operacao.imprimir_etiqueta(filial_id, pedido_id, dados, db, None)
