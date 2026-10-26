"""Contexto dos painéis: uma consulta central, independentemente do número de telas."""
import asyncio
import logging

from sqlalchemy import select

from ..core.presenca import sessoes_online
from ..models.models import ConfiguracaoOperacional, Filial, SessaoCopeira, Usuario

INTERVALO_CONTEXTO = 5
logger = logging.getLogger("cnutri.operacao")


def limites(config):
    return {campo: getattr(config, campo) if config is not None else 30
            for campo in ("preparo_minutos", "entrega_minutos")}


async def carregar_contexto(db, filiais: set[int]):
    unidades = [{"id": f.id, "nome": f.nome, "codigo_slug": f.codigo_slug}
                for f in await db.scalars(select(Filial).where(Filial.ativa.is_(True)).order_by(Filial.nome, Filial.id))]
    configuracoes = {c.filial_id: c for c in await db.scalars(
        select(ConfiguracaoOperacional).where(ConfiguracaoOperacional.filial_id.in_(filiais)))}
    contexto = {f: {"alertas": limites(configuracoes.get(f)), "copeiras": []} for f in filiais}
    online = sessoes_online(filiais).with_only_columns(SessaoCopeira.filial_id, Usuario.id, Usuario.nome).distinct().order_by(Usuario.nome, Usuario.id)
    for filial_id, usuario_id, nome in await db.execute(online):
        contexto[filial_id]["copeiras"].append({"id": usuario_id, "nome": nome})
    return unidades, contexto


class MonitorContexto:
    def __init__(self):
        self.anteriores = {}

    async def atualizar(self, sessoes, canais):
        filiais = {f for f, sockets in (*canais.ativos.items(), *canais.publicos.items()) if sockets}
        self.anteriores = {f: c for f, c in self.anteriores.items() if f in filiais}
        if not filiais:
            return
        async with sessoes() as db:
            unidades, contexto = await carregar_contexto(db, filiais)
        ativas = {u["id"] for u in unidades}
        for filial_id in filiais:
            if filial_id not in ativas:
                await canais.encerrar_unidade(filial_id)
                self.anteriores.pop(filial_id, None)
                continue
            atual = {"unidades": unidades, **contexto[filial_id]}
            anterior = self.anteriores.get(filial_id, {})
            publico = {k: atual[k] for k in ("unidades", "alertas") if atual[k] != anterior.get(k)}
            privado = {"copeiras": atual["copeiras"]} if atual["copeiras"] != anterior.get("copeiras") else {}
            if publico or privado:
                await canais.transmitir_contexto(filial_id, publico, privado)
            self.anteriores[filial_id] = atual


async def executar_contexto(sessoes, parar, canais):
    monitor = MonitorContexto()
    while not parar.is_set():
        try:
            await monitor.atualizar(sessoes, canais)
        except Exception:
            # Falhas temporárias não encerram o monitor; o HTTP continua disponível.
            logger.exception("contexto_indisponivel")
        try:
            await asyncio.wait_for(parar.wait(), timeout=INTERVALO_CONTEXTO)
        except TimeoutError:
            pass
