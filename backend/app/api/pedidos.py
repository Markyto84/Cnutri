"""Painel de produção da cozinha: Kanban, mudança de status e reimpressão."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..core.ws import gerenciador_ws
from ..models.models import Filial, HistoricoPedido, Pedido, Usuario
from ..schemas.schemas import PedidoOut, ReimpressaoCreate, StatusUpdate
from ..services.fila_impressao import enfileirar, resposta_fila
from ..services.operacao import pedido_operacional
from ..services.assistencia import registrar_etapa

router = APIRouter(prefix="/api/pedidos", tags=["Cozinha / Kanban"])
PERFIS_OPERACAO = ("COZINHA", "NUTRICIONISTA", "ADMIN_TI")


@router.get("")
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
    return [resposta_por_perfil(p, _) for p in pedidos]


def resposta_por_perfil(pedido, usuario):
    dados = PedidoOut.model_validate(pedido).model_dump(mode="json")
    return dados if usuario.perfil.nome in ("NUTRICIONISTA", "ADMIN_TI") else pedido_operacional(dados, autenticado=True)


@router.patch("/{pedido_id}/status")
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
    if anterior == "ENTREGUE":
        raise HTTPException(409, "Este pedido já foi entregue")
    if anterior == dados.status:
        return resposta_por_perfil(pedido, usuario)
    valores = {"status": dados.status}
    if dados.status == "PRONTO":
        valores["concluido_em"] = func.now()
    alterado = await db.scalar(
        update(Pedido).where(Pedido.id == pedido.id, Pedido.status == anterior)
        .values(**valores).returning(Pedido.id).execution_options(synchronize_session=False)
    )
    if alterado is None:
        raise HTTPException(409, "Outro painel já atualizou este pedido")
    db.add(
        HistoricoPedido(
            pedido_id=pedido.id,
            status_anterior=anterior,
            status_novo=dados.status,
            alterado_por_usuario_id=usuario.id,
        )
    )
    registrar_etapa(db, pedido, usuario, anterior, dados.status)
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])

    await gerenciador_ws.transmitir(
        pedido.filial_id,
        {
            "evento": "status_alterado",
            "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json"),
        },
    )
    return resposta_por_perfil(pedido, usuario)


@router.post("/{pedido_id}/reimprimir", status_code=202)
async def reimprimir(
    pedido_id: int, dados: ReimpressaoCreate | None = None,
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
    job = await enfileirar(db, pedido, filial, _.id, dados.confirmar_risco_duplicidade if dados else False)
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await gerenciador_ws.transmitir(pedido.filial_id, {"evento": "impressao_atualizada", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json")})
    return resposta_fila(job)
