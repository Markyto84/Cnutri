"""Administração de TI: filiais e utilizadores (Superadmin)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, hash_senha
from ..models.models import Filial, Perfil, Usuario, UsuarioFilial
from ..schemas.schemas import FilialCreate, FilialOut, UsuarioCreate, UsuarioOut

router = APIRouter(prefix="/api/admin", tags=["Administração"])


# ─── Filiais ─────────────────────────────────────────────────────────────────
@router.get("/filiais", response_model=list[FilialOut])
async def listar_filiais(db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    return (await db.execute(select(Filial).order_by(Filial.nome))).scalars().all()


@router.post("/filiais", response_model=FilialOut, status_code=status.HTTP_201_CREATED)
async def criar_filial(dados: FilialCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    existe = (
        await db.execute(select(Filial).where(Filial.codigo_slug == dados.codigo_slug))
    ).scalar_one_or_none()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma unidade com este código")
    filial = Filial(**dados.model_dump())
    db.add(filial)
    await db.commit()
    await db.refresh(filial)
    return filial


@router.patch("/filiais/{filial_id}", response_model=FilialOut)
async def atualizar_filial(filial_id: int, dados: FilialCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    filial = await db.get(Filial, filial_id)
    if filial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filial não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(filial, campo, valor)
    await db.commit()
    await db.refresh(filial)
    return filial


# ─── Utilizadores ────────────────────────────────────────────────────────────
@router.get("/usuarios", response_model=list[UsuarioOut])
async def listar_usuarios(db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    return (await db.execute(select(Usuario))).scalars().all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
async def criar_usuario(dados: UsuarioCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis("ADMIN_TI"))):
    email = dados.email.lower().strip()
    existe = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one_or_none()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")
    perfil = (
        await db.execute(select(Perfil).where(Perfil.nome == dados.perfil))
    ).scalar_one_or_none()
    if perfil is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Perfil inválido")

    usuario = Usuario(nome=dados.nome, email=email, senha_hash=hash_senha(dados.senha), perfil_id=perfil.id)
    db.add(usuario)
    await db.flush()
    for fid in dict.fromkeys(dados.filial_ids):
        if await db.get(Filial, fid) is not None:
            db.add(UsuarioFilial(usuario_id=usuario.id, filial_id=fid))
    await db.commit()
    await db.refresh(usuario)
    return usuario