"""Autenticação: login com e-mail/matrícula + palavra-passe (JWT)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import uuid4

from ..core.database import get_db
from ..core.security import criar_token, filiais_permitidas, get_current_user, oauth2_scheme, verificar_acesso_filial, verificar_senha
from ..core.config import settings
from ..core.presenca import TEMPO_PRESENCA, agora_utc
from ..models.models import SessaoCopeira, Usuario
from ..schemas.schemas import FilialOut, PresencaUpdate, TokenResponse, UsuarioOut

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    resultado = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfil)).where(
            Usuario.email == form.username.lower().strip()
        )
    )
    usuario = resultado.scalar_one_or_none()
    if usuario is None or not verificar_senha(form.password, usuario.senha_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou palavra-passe inválidos")
    if not usuario.ativo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Utilizador desativado")
    filiais = await filiais_permitidas(usuario, db)
    sessao_id = None
    if usuario.perfil.nome == "COPEIRA":
        sessao_id = str(uuid4())
        db.add(SessaoCopeira(id=sessao_id, usuario_id=usuario.id,
            filial_id=filiais[0].id if filiais else None, presenca_ate=agora_utc() + TEMPO_PRESENCA))
        await db.commit()
    return TokenResponse(
        access_token=criar_token(usuario, sessao_id),
        perfil=usuario.perfil.nome,
        nome=usuario.nome,
        usuario_id=usuario.id,
        filiais=[FilialOut.model_validate(f) for f in filiais],
    )


@router.get("/me", response_model=UsuarioOut)
async def perfil_atual(db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    dados = UsuarioOut.model_validate(usuario)
    return dados.model_copy(update={"filiais": [FilialOut.model_validate(f) for f in await filiais_permitidas(usuario, db)]})


@router.post("/presenca")
async def atualizar_presenca(dados: PresencaUpdate, token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if usuario.perfil.nome != "COPEIRA":
        raise HTTPException(403, "Presença disponível para o perfil Copeira")
    await verificar_acesso_filial(dados.filial_id, usuario, db)
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    sessao = await db.get(SessaoCopeira, payload["jti"])
    sessao.filial_id = dados.filial_id
    sessao.presenca_ate = agora_utc() + TEMPO_PRESENCA
    await db.commit()
    return {"online": True, "filial_id": dados.filial_id}


@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user)):
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    if usuario.perfil.nome == "COPEIRA" and payload.get("jti"):
        sessao = await db.get(SessaoCopeira, payload["jti"])
        sessao.encerrada_em = agora_utc()
        await db.commit()
    return {"saiu": True}
