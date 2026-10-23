"""Emissão e revogação de sessões autenticadas e das presenças vinculadas."""
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import update

from ..models.models import SessaoCopeira, SessaoUsuario
from ..schemas.schemas import FilialOut, TokenResponse
from .config import settings
from .presenca import TEMPO_PRESENCA, agora_utc
from .security import criar_token, filiais_permitidas


async def revogar_sessoes(db, usuario_id: int):
    agora = agora_utc()
    for modelo in (SessaoUsuario, SessaoCopeira):
        await db.execute(update(modelo).where(modelo.usuario_id == usuario_id, modelo.encerrada_em.is_(None)).values(encerrada_em=agora))


async def emitir_sessao(db, usuario, filial_id=None):
    filiais = await filiais_permitidas(usuario, db)
    identificador = str(uuid4())
    minutos = min(settings.JWT_EXPIRA_MINUTOS, settings.AD_SESSAO_MINUTOS) if usuario.origem_autenticacao == "AD" else settings.JWT_EXPIRA_MINUTOS
    db.add(SessaoUsuario(id=identificador, usuario_id=usuario.id, expira_em=agora_utc() + timedelta(minutes=minutos)))
    if usuario.perfil.nome == "COPEIRA" and not usuario.troca_senha_obrigatoria:
        unidade = next((f.id for f in filiais if f.id == filial_id), filiais[0].id if filiais else None)
        db.add(SessaoCopeira(id=identificador, usuario_id=usuario.id, filial_id=unidade, presenca_ate=agora_utc() + TEMPO_PRESENCA))
    await db.commit()
    return TokenResponse(access_token=criar_token(usuario, identificador), perfil=usuario.perfil.nome,
        nome=usuario.nome, usuario_id=usuario.id, troca_senha_obrigatoria=usuario.troca_senha_obrigatoria,
        origem_autenticacao=usuario.origem_autenticacao,
        filiais=[FilialOut.model_validate(f) for f in filiais])
