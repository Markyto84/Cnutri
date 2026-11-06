"""Fila durável de avisos; mudança de etapa e aviso são gravados juntos."""
import asyncio
from datetime import timedelta
import logging
from uuid import uuid4

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update

from ..core.presenca import agora_utc
from ..models.models import AvisoEmailPedido, ConfiguracaoEmailUnidade, ContatoEmailPedido, Filial, Pedido
from .email_medico import ErroEnvioEmail, compor_mensagem, obter_conexao, resumir_pedido, transportar_email

logger = logging.getLogger("cnutri.email")
TEMPO_VALIDO = timedelta(minutes=30)


async def enfileirar_aviso_pronto(db, pedido):
    if pedido.tipo_solicitacao != "MEDICO":
        return
    contato = await db.get(ContatoEmailPedido, pedido.id)
    if contato is None:
        return  # Pedidos anteriores ao recurso mantêm seu fluxo.
    existente = await db.scalar(select(AvisoEmailPedido.id).where(AvisoEmailPedido.pedido_id == pedido.id,
        AvisoEmailPedido.versao == pedido.versao))
    if existente is not None:
        return
    filial = await db.get(Filial, pedido.filial_id)
    config = await db.get(ConfiguracaoEmailUnidade, pedido.filial_id)
    habilitado = bool(config and config.habilitado)
    instante = agora_utc()
    dominio_mensagem = (config.remetente if config else contato.email).rsplit("@", 1)[-1]
    db.add(AvisoEmailPedido(pedido_id=pedido.id, filial_id=pedido.filial_id, versao=pedido.versao,
        destinatario=contato.email, resumo=await resumir_pedido(db, pedido, filial),
        mensagem_id=f"<cnutri-{uuid4().hex}@{dominio_mensagem}>", estado="PENDENTE" if habilitado else "DESATIVADO",
        erro=None if habilitado else "Envio desativado nesta unidade no momento em que a refeição ficou pronta",
        tentativas=0, proxima_tentativa_em=instante, expira_em=instante + TEMPO_VALIDO))


async def recuperar_interrompidos(sessoes):
    async with sessoes() as db:
        await db.execute(update(AvisoEmailPedido).where(AvisoEmailPedido.estado == "PROCESSANDO",
            AvisoEmailPedido.iniciado_em < agora_utc() - timedelta(minutes=3)).values(estado="INCERTO", reserva=None,
            erro="Processamento interrompido; confira o recebimento antes de reenviar"))
        await db.commit()


async def processar_um(sessoes):
    reserva = str(uuid4())
    async with sessoes() as db:
        aviso = await db.scalar(select(AvisoEmailPedido).where(AvisoEmailPedido.estado == "PENDENTE",
            AvisoEmailPedido.proxima_tentativa_em <= agora_utc()).order_by(AvisoEmailPedido.id).limit(1)
            .with_for_update(skip_locked=True))
        if aviso is None:
            return False
        alterado = await db.scalar(update(AvisoEmailPedido).where(AvisoEmailPedido.id == aviso.id, AvisoEmailPedido.estado == "PENDENTE")
            .values(estado="PROCESSANDO", reserva=reserva, iniciado_em=agora_utc(), tentativas=AvisoEmailPedido.tentativas + 1)
            .returning(AvisoEmailPedido.id).execution_options(synchronize_session=False))
        if alterado is None:
            return True
        aviso_id = aviso.id
        await db.commit()
    estado, erro, repetir = "ENVIADO", None, False
    try:
        async with sessoes() as db:
            aviso = await db.get(AvisoEmailPedido, aviso_id)
            pedido = await db.get(Pedido, aviso.pedido_id)
            filial = await db.get(Filial, aviso.filial_id)
            if pedido.status != "PRONTO" or pedido.versao != aviso.versao or not filial.ativa:
                estado, erro = "CANCELADO", "O pedido mudou de etapa, de versão ou a unidade foi desativada"
            elif aviso.expira_em <= agora_utc():
                estado, erro = "EXPIRADO", "A janela de 30 minutos para avisar a saída foi encerrada"
            else:
                conexao = await obter_conexao(db, aviso.filial_id)
                mensagem = compor_mensagem(conexao, aviso.destinatario, aviso.resumo, aviso.mensagem_id)
        if estado == "ENVIADO":
            await run_in_threadpool(transportar_email, conexao, mensagem)
    except ErroEnvioEmail as exc:
        estado, erro, repetir = "INCERTO" if exc.incerto else "FALHA", exc.mensagem, exc.repetir
    except HTTPException as exc:
        estado, erro = "FALHA", str(exc.detail)
    except Exception as exc:
        estado, erro = "FALHA", "Não foi possível preparar o aviso. Solicite a verificação pela TI"
        logger.error("preparacao_falhou aviso_id=%s tipo=%s", aviso_id, type(exc).__name__)
    async with sessoes() as db:
        aviso = await db.scalar(select(AvisoEmailPedido).where(AvisoEmailPedido.id == aviso_id,
            AvisoEmailPedido.reserva == reserva).with_for_update())
        if aviso is not None:
            aviso.estado, aviso.erro, aviso.reserva = estado, erro, None
            if repetir and aviso.tentativas < 3:
                aviso.estado = "PENDENTE"
                aviso.proxima_tentativa_em = agora_utc() + timedelta(seconds=30 * 2 ** (aviso.tentativas - 1))
            if estado == "ENVIADO":
                aviso.enviado_em = agora_utc()
            await db.commit()
    return True


async def executar_fila_email(sessoes, parar):
    while not parar.is_set():
        try:
            await recuperar_interrompidos(sessoes)
            if await processar_um(sessoes):
                continue
        except Exception as exc:
            logger.error("fila_indisponivel tipo=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(parar.wait(), timeout=5)
        except TimeoutError:
            pass
