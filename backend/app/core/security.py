"""Autenticação JWT e controle de perfis (RBAC)."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import settings
from .database import get_db
from ..models.models import Filial, SessaoCopeira, SessaoUsuario, Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

CREDENCIAIS_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Usuário ou senha inválidos",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    if len(senha.encode("utf-8")) > 72:
        return False
    return pwd_context.verify(senha, hash_)


def criar_token(usuario: Usuario, sessao_id: str) -> str:
    minutos = min(settings.JWT_EXPIRA_MINUTOS, settings.AD_SESSAO_MINUTOS) if usuario.origem_autenticacao == "AD" else settings.JWT_EXPIRA_MINUTOS
    expira = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    payload = {
        "sub": str(usuario.id),
        "perfil": usuario.perfil.nome,
        "nome": usuario.nome,
        "exp": expira,
    }
    if sessao_id:
        payload["jti"] = sessao_id
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> Usuario:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG], options={"require_exp": True, "require_sub": True, "require_jti": True})
        usuario_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise CREDENCIAIS_INVALIDAS
    usuario = (
        await db.execute(
            select(Usuario).options(selectinload(Usuario.perfil), selectinload(Usuario.filiais)).where(Usuario.id == usuario_id)
        )
    ).scalar_one_or_none()
    if usuario is None or not usuario.ativo:
        raise CREDENCIAIS_INVALIDAS
    if usuario.origem_autenticacao == "AD" and not settings.AD_HABILITADO:
        raise CREDENCIAIS_INVALIDAS
    sessao = await db.get(SessaoUsuario, payload["jti"])
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    if not sessao or sessao.usuario_id != usuario.id or sessao.encerrada_em or sessao.expira_em <= agora:
        raise CREDENCIAIS_INVALIDAS
    if usuario.perfil.nome == "COPEIRA" and not usuario.troca_senha_obrigatoria:
        sessao_id = payload.get("jti")
        sessao = await db.get(SessaoCopeira, sessao_id) if isinstance(sessao_id, str) else None
        if not sessao or sessao.usuario_id != usuario.id or sessao.encerrada_em is not None:
            raise CREDENCIAIS_INVALIDAS
    return usuario


async def filiais_permitidas(usuario: Usuario, db: AsyncSession) -> list[Filial]:
    if usuario.perfil.nome == "ADMIN_TI":
        return list((await db.execute(select(Filial).order_by(Filial.nome))).scalars().all())
    return sorted((f for f in usuario.filiais if f.ativa), key=lambda f: f.nome)


async def usuario_opcional(token: str | None = Depends(oauth2_opcional), db: AsyncSession = Depends(get_db)):
    if token is None:
        return None
    usuario = await get_current_user(token, db)
    if usuario.troca_senha_obrigatoria:
        raise HTTPException(403, "Atualize sua senha antes de continuar")
    return usuario


async def verificar_acesso_filial(filial_id: int, usuario: Usuario, db: AsyncSession) -> Filial:
    filial = await db.get(Filial, filial_id)
    if filial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unidade não encontrada")
    if usuario.perfil.nome != "ADMIN_TI" and (
        not filial.ativa or not any(f.id == filial_id for f in usuario.filiais)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu usuário não tem acesso a esta unidade")
    return filial


def exigir_perfis(*perfis: str):
    """Fábrica de dependência: restringe a rota a determinados perfis."""

    async def _dep(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.troca_senha_obrigatoria:
            raise HTTPException(403, "Atualize sua senha antes de continuar")
        if usuario.perfil.nome not in perfis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso restrito a este perfil")
        return usuario

    return _dep
