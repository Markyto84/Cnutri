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
from ..models.models import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

CREDENCIAIS_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="E-mail ou palavra-passe inválidos",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    return pwd_context.verify(senha, hash_)


def criar_token(usuario: Usuario) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRA_MINUTOS)
    payload = {
        "sub": str(usuario.id),
        "perfil": usuario.perfil.nome,
        "nome": usuario.nome,
        "exp": expira,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> Usuario:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        usuario_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise CREDENCIAIS_INVALIDAS
    usuario = (
        await db.execute(
            select(Usuario).options(selectinload(Usuario.perfil)).where(Usuario.id == usuario_id)
        )
    ).scalar_one_or_none()
    if usuario is None or not usuario.ativo:
        raise CREDENCIAIS_INVALIDAS
    return usuario


def exigir_perfis(*perfis: str):
    """Fábrica de dependência: restringe a rota a determinados perfis."""

    async def _dep(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.perfil.nome not in perfis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso restrito a este perfil")
        return usuario

    return _dep