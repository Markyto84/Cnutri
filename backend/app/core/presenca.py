"""Presença das copeiras por sessão e unidade, compartilhada entre processos da API."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..models.models import Perfil, SessaoCopeira, Usuario, UsuarioFilial

TEMPO_PRESENCA = timedelta(minutes=3)


def agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sessoes_online(filial_id: int):
    return (
        select(SessaoCopeira)
        .join(Usuario, Usuario.id == SessaoCopeira.usuario_id)
        .join(Perfil, Perfil.id == Usuario.perfil_id)
        .join(UsuarioFilial, UsuarioFilial.usuario_id == Usuario.id)
        .where(
            SessaoCopeira.filial_id == filial_id,
            UsuarioFilial.filial_id == filial_id,
            SessaoCopeira.encerrada_em.is_(None),
            SessaoCopeira.presenca_ate > agora_utc(),
            Usuario.ativo.is_(True), Perfil.nome == "COPEIRA",
        )
    )
