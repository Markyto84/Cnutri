"""Painel de produção da cozinha: Kanban, mudança de status e reimpressão."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..core.ws import gerenciador_ws
from ..models.models import Filial, HistoricoPedido, Pedido, Usuario
from ..schemas.schemas import PedidoOut, StatusUpdate
from ..services.impressora import imprimir_filipeta, montar_filipeta_configurada

router = APIRouter(prefix="/api/pedidos", tags=["Cozinha / Kanban"])
PERFIS_OPERACAO = ("COZINHA", "NUTRICIONISTA", "ADMIN_TI")


@router.get("", response_model=list[PedidoOut])
async def listar_pedidos(
    filial_id: int,
    status_filtro: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(exigir_perfis(*PERFIS_OPERACAO)),
):
    await verificar_acesso_filial(filial_id, _, db)
    consulta = (
        select(Pedido)
        .options(selectinload(Pedido.dieta))
        .where(Pedido.filial_id == filial_id)
        .order_by(Pedido.criado_em.desc())
        .limit(200)
    )
    if status_filtro:
        consulta = consulta.where(Pedido.status == status_filtro)
    pedidos = (await db.execute(consulta)).scalars().all()
    return pedidos


@router.patch("/{pedido_id}/status", response_model=PedidoOut)
async def alterar_status(
    pedido_id: int,
    dados: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis(*PERFIS_OPERACAO)),
):
    pedido = (
        await db.execute(
            select(Pedido).options(selectinload(Pedido.dieta)).where(Pedido.id == pedido_id)
        )
    ).scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido não encontrado")
    await verificar_acesso_filial(pedido.filial_id, usuario, db)

    anterior = pedido.status
    if anterior == dados.status:
        return pedido
    pedido.status = dados.status
    if dados.status == "PRONTO":
        pedido.concluido_em = func.now()  # relógio do banco (evita conflito de timezone no asyncpg)
    db.add(
        HistoricoPedido(
            pedido_id=pedido.id,
            status_anterior=anterior,
            status_novo=dados.status,
            alterado_por_usuario_id=usuario.id,
        )
    )
    await db.commit()
    await db.refresh(pedido)

    await gerenciador_ws.transmitir(
        pedido.filial_id,
        {
            "evento": "status_alterado",
            "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json"),
        },
    )
    return pedido


@router.post("/{pedido_id}/reimprimir")
async def reimprimir(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(exigir_perfis(*PERFIS_OPERACAO)),
):
    pedido = (
        await db.execute(
            select(Pedido).options(selectinload(Pedido.dieta), selectinload(Pedido.filial)).where(Pedido.id == pedido_id)
        )
    ).scalar_one_or_none()
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido não encontrado")
    await verificar_acesso_filial(pedido.filial_id, _, db)

    filial: Filial = pedido.filial
    if not filial.ip_impressora:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impressora não configurada para esta unidade")

    buffer = await montar_filipeta_configurada(db, pedido, filial, pedido.dieta)
    ok = imprimir_filipeta(filial.ip_impressora, buffer)
    if ok:
        db.add(
            HistoricoPedido(
                pedido_id=pedido.id,
                status_anterior=pedido.status,
                status_novo=pedido.status,
                alterado_por_usuario_id=_.id,
                impresso=True,
            )
        )
        await db.commit()
    return {"impresso": ok}
