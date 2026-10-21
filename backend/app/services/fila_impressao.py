"""Fila durável. Falhas antes da conexão têm retry; envios incertos exigem conferência humana."""
import asyncio
from datetime import timedelta
import logging
from uuid import uuid4

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload, undefer

from ..core.presenca import agora_utc
from ..core.ws import gerenciador_ws
from ..models.models import Filial, HistoricoPedido, Pedido, TrabalhoImpressao
from ..schemas.schemas import PedidoOut
from .impressora import ErroEnvioImpressora, enviar_filipeta, montar_filipeta_configurada

logger = logging.getLogger("cnutri.impressao")
ATIVOS = ("PENDENTE", "PROCESSANDO")


async def enfileirar(db, pedido, filial, usuario_id=None, confirmar=False):
    # Serializa cliques no mesmo pedido; o índice parcial também protege a gravação.
    await db.scalar(select(Pedido.id).where(Pedido.id == pedido.id).with_for_update())
    ultimo = await db.scalar(select(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido.id).order_by(TrabalhoImpressao.id.desc()).limit(1))
    if ultimo and ultimo.estado in ATIVOS:
        return ultimo
    if ultimo and ultimo.estado == "INCERTO" and not confirmar:
        raise HTTPException(409, "O envio anterior foi interrompido e pode ter saído no papel. Confira a impressora e confirme o novo envio")
    job = TrabalhoImpressao(pedido_id=pedido.id, solicitado_por_usuario_id=usuario_id,
        estado="PENDENTE" if filial.ip_impressora else "FALHA",
        erro=None if filial.ip_impressora else "Impressora não configurada para esta unidade", tentativas=0, proxima_tentativa_em=agora_utc())
    db.add(job)
    await db.flush()
    return job


def resposta_fila(job):
    return {"enfileirado": job.estado in ATIVOS, "impresso": False, "impressao": {
        "id": job.id, "estado": job.estado, "tentativas": job.tentativas, "erro": job.erro}}


async def notificar_pedido(sessoes, pedido_id):
    async with sessoes() as db:
        pedido = await db.scalar(select(Pedido).options(selectinload(Pedido.dieta)).where(Pedido.id == pedido_id))
        if pedido:
            await gerenciador_ws.transmitir(pedido.filial_id, {"evento": "impressao_atualizada", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json")})


async def recuperar_interrompidos(sessoes):
    async with sessoes() as db:
        pedidos = (await db.execute(update(TrabalhoImpressao).where(
            TrabalhoImpressao.estado == "PROCESSANDO", TrabalhoImpressao.iniciado_em < agora_utc() - timedelta(seconds=60))
            .values(estado="INCERTO", reserva=None, erro="Envio interrompido. Confira o papel antes de reenviar")
            .returning(TrabalhoImpressao.pedido_id))).scalars().all()
        await db.commit()
    for pedido_id in pedidos:
        await notificar_pedido(sessoes, pedido_id)


async def processar_um(sessoes):
    reserva = str(uuid4())
    async with sessoes() as db:
        job = await db.scalar(select(TrabalhoImpressao).where(TrabalhoImpressao.estado == "PENDENTE",
            TrabalhoImpressao.proxima_tentativa_em <= agora_utc()).order_by(TrabalhoImpressao.id).limit(1).with_for_update(skip_locked=True))
        if not job:
            return False
        alterado = await db.scalar(update(TrabalhoImpressao).where(TrabalhoImpressao.id == job.id, TrabalhoImpressao.estado == "PENDENTE")
            .values(estado="PROCESSANDO", reserva=reserva, iniciado_em=agora_utc(), tentativas=TrabalhoImpressao.tentativas + 1)
            .returning(TrabalhoImpressao.id).execution_options(synchronize_session=False))
        if alterado is None:
            return True
        job_id, pedido_id = job.id, job.pedido_id
        await db.commit()
    await notificar_pedido(sessoes, pedido_id)
    estado, erro, repetir = "ENVIADO", None, False
    try:
        async with sessoes() as db:
            job = await db.scalar(select(TrabalhoImpressao).options(undefer(TrabalhoImpressao.dados)).where(TrabalhoImpressao.id == job_id))
            pedido = await db.scalar(select(Pedido).options(selectinload(Pedido.dieta)).where(Pedido.id == pedido_id))
            filial = await db.get(Filial, pedido.filial_id)
            if pedido.status == "CANCELADO":
                estado = "CANCELADO"
            elif not filial.ip_impressora:
                estado, erro = "FALHA", "Impressora não configurada para esta unidade"
            else:
                if job.dados is None:
                    job.dados = await montar_filipeta_configurada(db, pedido, filial, pedido.dieta)
                    await db.commit()  # mantém o mesmo documento nas novas tentativas.
                dados, destino = job.dados, filial.ip_impressora
                # Não mantenha conexão/transação do banco ocupada durante o envio TCP.
                await db.rollback()
        if estado == "ENVIADO":
            await run_in_threadpool(enviar_filipeta, destino, dados)
    except ErroEnvioImpressora as exc:
        estado = "INCERTO" if exc.incerto else "FALHA"
        erro = "Confira o papel antes de reenviar: o envio pode ter sido parcial" if exc.incerto else "Impressora sem conexão"
        repetir = not exc.incerto
    except Exception as exc:
        estado, erro = "FALHA", "Não foi possível preparar a filipeta. Solicite a verificação pela gestão"
        logger.error("preparacao_falhou trabalho_id=%s tipo=%s", job_id, type(exc).__name__)
    async with sessoes() as db:
        job = await db.scalar(select(TrabalhoImpressao).where(TrabalhoImpressao.id == job_id, TrabalhoImpressao.reserva == reserva).with_for_update())
        if job is not None:
            job.estado, job.erro, job.reserva = estado, erro, None
            if repetir and job.tentativas < 3:
                job.estado = "PENDENTE"
                job.proxima_tentativa_em = agora_utc() + timedelta(seconds=15 * job.tentativas)
            if estado == "ENVIADO":
                job.enviado_em = agora_utc()
                pedido = await db.get(Pedido, pedido_id)
                db.add(HistoricoPedido(pedido_id=pedido_id, status_anterior=pedido.status, status_novo=pedido.status,
                    alterado_por_usuario_id=job.solicitado_por_usuario_id, impresso=True))
            await db.commit()
    await notificar_pedido(sessoes, pedido_id)
    return True


async def executar_fila(sessoes, parar):
    while not parar.is_set():
        try:
            await recuperar_interrompidos(sessoes)
            if await processar_um(sessoes):
                continue
        except Exception as exc:
            logger.error("fila_indisponivel tipo=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(parar.wait(), timeout=1)
        except TimeoutError:
            pass
