"""Cozinha e entregas por unidade, sem exigir login para abrir os painéis."""
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, usuario_opcional, verificar_acesso_filial
from ..core.presenca import sessoes_online
from ..core.ws import gerenciador_ws
from ..models.models import EntregaPedido, Filial, HistoricoPedido, ImpressoraEtiqueta, Pedido, RecebimentoEntrega, SessaoCopeira, Usuario
from ..schemas.schemas import EntregaCreate, PedidoOut, ReimpressaoCreate, StatusUpdate
from ..services.fila_impressao import enfileirar, resposta_fila
from ..services.operacao import data_utc, pedido_operacional
from ..modules.assinatura import gerar_assinatura_png
from ..services.etiquetas import campos_etiqueta, destinatarios_etiqueta, nome_etiqueta, previa_png
from ..services.assistencia import registrar_etapa, registrar_evento
from ..services.contexto_operacao import carregar_contexto

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


def serializar(pedido: Pedido, autenticado=True) -> dict:
    return pedido_operacional(PedidoOut.model_validate(pedido).model_dump(mode="json"), autenticado=autenticado)


async def notificar(pedido: Pedido):
    await gerenciador_ws.transmitir(pedido.filial_id, {
        "evento": "status_alterado", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json"),
    })


@router.get("/unidades")
async def listar_unidades(db: AsyncSession = Depends(get_db)):
    filiais = (await db.execute(select(Filial).where(Filial.ativa.is_(True)).order_by(Filial.nome))).scalars().all()
    return [{"id": f.id, "nome": f.nome, "codigo_slug": f.codigo_slug} for f in filiais]


@router.get("/unidades/{filial_id}/pedidos")
async def listar_pedidos(filial_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(usuario_opcional)):
    await unidade_ativa(filial_id, db)
    if usuario:
        await verificar_acesso_filial(filial_id, usuario, db)
    pedidos = (await db.execute(select(Pedido).options(selectinload(Pedido.dieta)).where(
        Pedido.filial_id == filial_id, Pedido.status.in_(STATUS_ATIVOS),
    ).order_by(Pedido.criado_em))).scalars().all()
    return [serializar(pedido, autenticado=usuario is not None) for pedido in pedidos]


@router.get("/unidades/{filial_id}/copeiras")
async def listar_copeiras_online(filial_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(usuario_opcional)):
    await unidade_ativa(filial_id, db)
    if not usuario:
        return []
    await verificar_acesso_filial(filial_id, usuario, db)
    ids = sessoes_online(filial_id).with_only_columns(SessaoCopeira.usuario_id)
    pessoas = (await db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(ids)).order_by(Usuario.nome))).all()
    return [{"id": pessoa.id, "nome": pessoa.nome} for pessoa in pessoas]


@router.get("/unidades/{filial_id}/estado")
async def estado_painel(filial_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       usuario: Usuario | None = Depends(usuario_opcional)):
    # Autorização sempre precede o ETag, inclusive para uma resposta sem alterações.
    await unidade_ativa(filial_id, db)
    if usuario:
        await verificar_acesso_filial(filial_id, usuario, db)
    unidades, contexto = await carregar_contexto(db, {filial_id})
    pedidos = (await db.scalars(select(Pedido).options(selectinload(Pedido.dieta)).where(
        Pedido.filial_id == filial_id, Pedido.status.in_(STATUS_ATIVOS),
    ).order_by(Pedido.criado_em, Pedido.id))).all()
    resposta = JSONResponse({"unidades": unidades, "alertas": contexto[filial_id]["alertas"],
        "pedidos": [serializar(p, autenticado=usuario is not None) for p in pedidos],
        "copeiras": contexto[filial_id]["copeiras"] if usuario else []})
    escopo = f'{filial_id}:{usuario.id if usuario else "publico"}:'.encode()
    etag = '"' + sha256(escopo + resposta.body).hexdigest() + '"'
    cabecalhos = {"ETag": etag, "Cache-Control": "private, no-store", "Vary": "Authorization"}
    if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=cabecalhos)
    resposta.headers.update(cabecalhos)
    return resposta


@router.patch("/unidades/{filial_id}/pedidos/{pedido_id}/status")
async def alterar_status(filial_id: int, pedido_id: int, dados: StatusUpdate, db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(OPERADORES)):
    if usuario:
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
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior=anterior, status_novo=dados.status, alterado_por_usuario_id=usuario.id if usuario else None))
    registrar_etapa(db, pedido, usuario, anterior, dados.status, dados.motivo if dados.status == "CANCELADO" else None)
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await notificar(pedido)
    return serializar(pedido)


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/reimprimir", status_code=202)
async def reimprimir(filial_id: int, pedido_id: int, dados: ReimpressaoCreate | None = None, db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(OPERADORES)):
    if usuario:
        await verificar_acesso_filial(filial_id, usuario, db)
    pedido = await obter_pedido(filial_id, pedido_id, db)
    filial = await unidade_ativa(filial_id, db)
    job = await enfileirar(db, pedido, filial, usuario.id if usuario else None, dados.confirmar_risco_duplicidade if dados else False)
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await notificar(pedido)
    return resposta_fila(job)


@router.get("/unidades/{filial_id}/pedidos/{pedido_id}/etiqueta")
async def previa_etiqueta(filial_id: int, pedido_id: int, indice: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(OPERADORES)):
    filial = await verificar_acesso_filial(filial_id, usuario, db) if usuario else await unidade_ativa(filial_id, db)
    pedido = await obter_pedido(filial_id, pedido_id, db)
    if pedido.status != "PRONTO":
        raise HTTPException(409, "A etiqueta só está disponível para refeições prontas")
    if not nome_etiqueta(pedido).strip():
        raise HTTPException(422, "Este pedido não possui nome do destinatário para gerar a etiqueta")
    destinatarios = destinatarios_etiqueta(pedido)
    if indice >= len(destinatarios):
        raise HTTPException(404, "Esta etiqueta não faz parte do pedido")
    destinatario = destinatarios[indice]
    impressora = await db.get(ImpressoraEtiqueta, filial_id)
    try:
        imagem = await run_in_threadpool(previa_png, campos_etiqueta(pedido, filial, destinatario),
            impressora.resolucao if impressora else 203, destinatario == "Acompanhante")
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from None
    return Response(imagem, media_type="image/png", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "X-Quantidade-Etiquetas": str(len(destinatarios)), "X-Destinatario-Etiqueta": destinatario})


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/etiqueta", status_code=202)
async def imprimir_etiqueta(filial_id: int, pedido_id: int, dados: ReimpressaoCreate | None = None,
    db: AsyncSession = Depends(get_db), usuario: Usuario | None = Depends(OPERADORES)):
    if usuario:
        await verificar_acesso_filial(filial_id, usuario, db)
    pedido = await obter_pedido(filial_id, pedido_id, db)
    filial = await unidade_ativa(filial_id, db)
    job = await enfileirar(db, pedido, filial, usuario.id if usuario else None, dados.confirmar_risco_duplicidade if dados else False, tipo="ETIQUETA")
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await notificar(pedido)
    return resposta_fila(job)


@router.post("/unidades/{filial_id}/pedidos/{pedido_id}/entregar", status_code=201)
async def entregar(filial_id: int, pedido_id: int, request: Request, dados: EntregaCreate | None = None,
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(ENTREGADORES)):
    await verificar_acesso_filial(filial_id, usuario, db)
    dados = dados or EntregaCreate()
    if usuario.perfil.nome == "COPEIRA":
        if dados.copeira_id is not None and dados.copeira_id != usuario.id:
            raise HTTPException(403, "A copeira deve registrar a própria entrega")
        copeira_id = usuario.id
    else:
        copeira_id = dados.copeira_id
        if copeira_id is None:
            raise HTTPException(422, "Selecione a copeira do plantão responsável pela entrega")
    pedido = await obter_pedido(filial_id, pedido_id, db)
    if pedido.status != "PRONTO":
        raise HTTPException(409, "Somente refeições prontas podem ser entregues")
    sessao = (await db.execute(sessoes_online(filial_id).where(
        SessaoCopeira.usuario_id == copeira_id,
    ).limit(1).with_for_update(of=SessaoCopeira))).scalar_one_or_none()
    if sessao is None:
        raise HTTPException(409, "Esta copeira não está mais online nesta unidade. Selecione outra copeira do plantão")
    copeira = await db.get(Usuario, copeira_id)
    alterado = await db.scalar(update(Pedido).where(Pedido.id == pedido.id, Pedido.status == "PRONTO")
        .values(status="ENTREGUE").returning(Pedido.id).execution_options(synchronize_session=False))
    if alterado is None:
        raise HTTPException(409, "Outro painel já entregou ou atualizou esta refeição")
    entrega = EntregaPedido(pedido_id=pedido.id, copeira_id=copeira.id, copeira_nome=copeira.nome,
        registrado_por_usuario_id=usuario.id, ip_origem=request.client.host if request.client else None)
    db.add(entrega)
    await db.flush()
    assinatura_registrada = dados.assinatura is not None
    if assinatura_registrada:
        db.add(RecebimentoEntrega(pedido_id=pedido.id, recebedor_nome=dados.recebedor_nome,
            assinatura_png=gerar_assinatura_png(dados.assinatura)))
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior="PRONTO", status_novo="ENTREGUE",
        alterado_por_usuario_id=usuario.id))
    registrar_etapa(db, pedido, usuario, "PRONTO", "ENTREGUE")
    registrar_evento(db, pedido, "ENTREGA_REGISTRADA", usuario, depois={"copeira_id": copeira.id,
        "copeira_nome": copeira.nome, "recebedor_nome": dados.recebedor_nome, "assinatura_registrada": assinatura_registrada})
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await db.refresh(entrega)
    await notificar(pedido)
    return {"pedido_id": pedido.id, "status": "ENTREGUE", "copeira_id": entrega.copeira_id,
        "copeira_nome": entrega.copeira_nome, "entregue_em": data_utc(entrega.entregue_em),
        "recebedor_nome": dados.recebedor_nome, "assinatura_registrada": assinatura_registrada}
