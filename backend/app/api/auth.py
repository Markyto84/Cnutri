"""Autenticação: login com e-mail/matrícula + palavra-passe (JWT)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import criar_token, filiais_permitidas, get_current_user, verificar_senha
from ..models.models import Usuario
from ..schemas.schemas import FilialOut, TokenResponse, UsuarioOut

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
    return TokenResponse(
        access_token=criar_token(usuario),
        perfil=usuario.perfil.nome,
        nome=usuario.nome,
        usuario_id=usuario.id,
        filiais=[FilialOut.model_validate(f) for f in await filiais_permitidas(usuario, db)],
    )


@router.get("/me", response_model=UsuarioOut)
async def perfil_atual(db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    dados = UsuarioOut.model_validate(usuario)
    return dados.model_copy(update={"filiais": [FilialOut.model_validate(f) for f in await filiais_permitidas(usuario, db)]})
