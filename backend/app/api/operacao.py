"""Cozinha e entregas por unidade, sem exigir login para abrir os painéis."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..core.presenca import sessoes_online
from ..core.ws import gerenciador_ws
from ..models.models import EntregaPedido, Filial, HistoricoPedido, Pedido, RecebimentoEntrega, SessaoCopeira, Usuario
from ..schemas.schemas import EntregaCreate, PedidoOut, StatusUpdate
from ..services.impressora import imprimir_filipeta, montar_filipeta_configurada
from ..services.operacao import data_utc, pedido_operacional
from ..services.assinatura import gerar_assinatura_png

router = APIRouter(prefix="/api/operacao", tags=["Dashboard e entregas"])
STATUS_ATIVOS = ("PENDENTE", "EM_PREPARO", "PRONTO")
OPERADORES = exigir_perfis("COZINHA", "NUTRICIONISTA", "ADMIN_TI")
ENTREGADORES = exigir_perfis("COPEIRA", "NUTRICIONISTA", "ADMIN_TI")


async def unidade_ativa(filial_id: int, db: AsyncSession) -> Filial:
    filial = await db.get(Filial, filial_id)
    if not filial or not filial.ativa:
        raise HTTPException(404, "Unidade indisponível")
    return filial


async def obter_pedido(filial_id: int, pedido_id: int, db: AsyncSession) -> Pedido:
    await unidade_ativa(filial_id, db)
    pedido = (await db.execute(select(Pedido).options(selectinload(Pedido.dieta)).where(
        Pedido.id == pedido_id, Pedido.filial_id == filial_id,
    ))).scalar_one_or_none()
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado nesta unidade")
    return pedido


def serializar(pedido: Pedido) -> dict:
    return pedido_operacional(PedidoOut.model_validate(pedido).model_dump(mode="json"))


async def notificar(pedido: Pedido):
    await gerenciador_ws.transmitir(pedido.filial_id, {
        "evento": "status_alterado", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json"),
    })


@router.get("/unidades")
async def listar_unidades(db: AsyncSession = Depends(get_db)):
    filiais = (await db.execute(select(Filial).where(Filial.ativa.is_(True)).order_by(Filial.nome))).scalars().all()
    return [{"id": f.id, "nome": f.nome, "codigo_slug": f.codigo_slug} for f in filiais]


@router.get("/unidades/{filial_id}/pedidos")
async def listar_pedidos(filial_id: int, db: AsyncSession = Depends(get_db)):
    await unidade_ativa(filial_id, db)
    pedidos = (await db.execute(select(Pedido).options(selectinload(Pedido.dieta)).where(
        Pedido.filial_id == filial_id, Pedido.status.in_(STATUS_ATIVOS),
    ).order_by(Pedido.criado_em))).scalars().all()
    return [serializar(pedido) for pedido in pedidos]


@router.get("/unidades/{filial_id}/copeiras")
async def listar_copeiras_online(filial_id: int, db: AsyncSession = Depends(get_db)):
    await unidade_ativa(filial_id, db)
    ids = sessoes_online(filial_id).with_only_columns(SessaoCopeira.usuario_id)
    pessoas = (await db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(ids)).order_by(Usuario.nome))).all()
    return [{"id": pessoa.id, "nome": pessoa.nome} for pessoa in pessoas]


@router.patch("/unidades/{filial_id}/pedidos/{pedido_id}/status")
async def alterar_status(filial_id: int, pedido_id: int, dados: StatusUpdate, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(OPERADORES)):
    await verificar_acesso_filial(filial_id, usuario, db)
    pedido = await obter_pedido(filial_id, pedido_id, db)
    anterior = pedido.status
    if anterior not in STATUS_ATIVOS:
        raise HTTPException(409, "Este pedido já foi entregue ou cancelado")
    if anterior == dados.status:
        return serializar(pedido)
    permitido = {"PENDENTE": "EM_PREPARO", "EM_PREPARO": "PRONTO"}.get(anterior)
    if dados.status not in (permitido, "CANCELADO"):
        raise HTTPException(409, "A etapa do pedido mudou. Atualize o painel")
    valores = {"status": dados.status}
    if dados.status == "PRONTO":
        valores["concluido_em"] = func.now()
    alterado = await db.scalar(update(Pedido).where(Pedido.id == pedido.id, Pedido.status == anterior)
        .values(**valores).returning(Pedido.id).execution_options(synchronize_session=False))
    if alterado is None:
        raise HTTPException(409, "Outro painel já atualizou este pedido")
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior=anterior, status_novo=dados.status, alterado_por_usuario_id=usuario.id))
    await db.commit()
    await db.refresh(pedido)
    await notificar(pedido)
    return serializar(pedido)


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/reimprimir")
async def reimprimir(filial_id: int, pedido_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(OPERADORES)):
    await verificar_acesso_filial(filial_id, usuario, db)
    pedido = await obter_pedido(filial_id, pedido_id, db)
    filial = await unidade_ativa(filial_id, db)
    if not filial.ip_impressora:
        raise HTTPException(400, "Impressora não configurada para esta unidade")
    buffer = await montar_filipeta_configurada(db, pedido, filial, pedido.dieta)
    ok = imprimir_filipeta(filial.ip_impressora, buffer)
    if ok:
        db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior=pedido.status, status_novo=pedido.status, impresso=True, alterado_por_usuario_id=usuario.id))
        await db.commit()
    return {"impresso": ok}


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/entregar", status_code=201)
async def entregar(filial_id: int, pedido_id: int, dados: EntregaCreate, request: Request,
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(ENTREGADORES)):
    await verificar_acesso_filial(filial_id, usuario, db)
    if usuario.perfil.nome == "COPEIRA" and dados.copeira_id != usuario.id:
        raise HTTPException(403, "A copeira deve registrar a própria entrega")
    pedido = await obter_pedido(filial_id, pedido_id, db)
    if pedido.status != "PRONTO":
        raise HTTPException(409, "Somente refeições prontas podem ser entregues")
    sessao = (await db.execute(sessoes_online(filial_id).where(
        SessaoCopeira.usuario_id == dados.copeira_id,
    ).limit(1).with_for_update(of=SessaoCopeira))).scalar_one_or_none()
    if sessao is None:
        raise HTTPException(409, "Esta copeira não está mais online nesta unidade. Selecione outra copeira do plantão")
    copeira = await db.get(Usuario, dados.copeira_id)
    alterado = await db.scalar(update(Pedido).where(Pedido.id == pedido.id, Pedido.status == "PRONTO")
        .values(status="ENTREGUE").returning(Pedido.id).execution_options(synchronize_session=False))
    if alterado is None:
        raise HTTPException(409, "Outro painel já entregou ou atualizou esta refeição")
    entrega = EntregaPedido(pedido_id=pedido.id, copeira_id=copeira.id, copeira_nome=copeira.nome,
        registrado_por_usuario_id=usuario.id, ip_origem=request.client.host if request.client else None)
    db.add(entrega)
    await db.flush()
    db.add(RecebimentoEntrega(pedido_id=pedido.id, recebedor_nome=dados.recebedor_nome,
        assinatura_png=gerar_assinatura_png(dados.assinatura)))
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior="PRONTO", status_novo="ENTREGUE",
        alterado_por_usuario_id=usuario.id))
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(entrega)
    await notificar(pedido)
    return {"pedido_id": pedido.id, "status": "ENTREGUE", "copeira_id": entrega.copeira_id,
        "copeira_nome": entrega.copeira_nome, "entregue_em": data_utc(entrega.entregue_em),
        "recebedor_nome": dados.recebedor_nome, "assinatura_registrada": True}
