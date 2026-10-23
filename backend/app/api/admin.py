"""Administração de unidades, credenciais e impressoras."""
import asyncio
from copy import deepcopy
import socket
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, hash_senha
from ..core.sessoes import revogar_sessoes
from ..core.ws import gerenciador_ws
from ..services.active_directory import situacao_ad
from ..models.models import Dieta, Filial, FormularioConfig, ImpressoraEtiqueta, Perfil, Usuario
from ..schemas.schemas import FilialCreate, FilialOut, FilialUpdate, ImpressoraUpdate, ImpressoraEtiquetaOut, ImpressoraEtiquetaUpdate, UsuarioCreate, UsuarioOut, UsuarioUpdate
from .gestao import ESQUEMA_PADRAO_ENFERMAGEM, ESQUEMA_PADRAO_MEDICO

router = APIRouter(prefix="/api/admin", tags=["Administração"])
ADMIN = exigir_perfis("ADMIN_TI")


async def unidade(filial_id: int, db: AsyncSession) -> Filial:
    filial = await db.get(Filial, filial_id)
    if filial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unidade não encontrada")
    return filial


async def confirmar(db: AsyncSession, mensagem: str) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, mensagem)


# ─── Filiais ─────────────────────────────────────────────────────────────────
@router.get("/filiais", response_model=list[FilialOut])
async def listar_filiais(db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    return (await db.execute(select(Filial).order_by(Filial.nome))).scalars().all()


@router.post("/filiais", response_model=FilialOut, status_code=status.HTTP_201_CREATED)
async def criar_filial(dados: FilialCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    existe = (
        await db.execute(select(Filial).where(Filial.codigo_slug == dados.codigo_slug))
    ).scalar_one_or_none()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma unidade com este código")
    if dados.origem_filial_id:
        origem = await unidade(dados.origem_filial_id, db)
    else:
        origem = (await db.execute(select(Filial).order_by(Filial.id).limit(1))).scalar_one_or_none()
    esquemas, dietas = {}, []
    if origem:
        configs = (await db.execute(select(FormularioConfig).where(FormularioConfig.filial_id == origem.id))).scalars().all()
        esquemas = {c.tipo_publico: c.esquema_json for c in configs}
        dietas = list((await db.execute(select(Dieta).where(Dieta.filial_id == origem.id))).scalars().all())
    filial = Filial(**dados.model_dump(exclude={"origem_filial_id"}))
    db.add(filial)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma unidade com este código")
    for tipo, padrao in (("MEDICO", ESQUEMA_PADRAO_MEDICO), ("ENFERMAGEM", ESQUEMA_PADRAO_ENFERMAGEM)):
        db.add(FormularioConfig(filial_id=filial.id, tipo_publico=tipo, esquema_json=deepcopy(esquemas.get(tipo, padrao))))
    for dieta in dietas:
        db.add(Dieta(filial_id=filial.id, nome=dieta.nome, descricao=dieta.descricao, severa=dieta.severa, ativa=dieta.ativa))
    await confirmar(db, "Já existe uma unidade com este código")
    await db.refresh(filial)
    return filial


@router.patch("/filiais/{filial_id}", response_model=FilialOut)
async def atualizar_filial(filial_id: int, dados: FilialUpdate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    filial = await unidade(filial_id, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(filial, campo, valor)
    await confirmar(db, "Já existe uma unidade com este código")
    await db.refresh(filial)
    if not filial.ativa:
        await gerenciador_ws.encerrar_unidade(filial.id)
    return filial


@router.patch("/filiais/{filial_id}/impressora", response_model=FilialOut)
async def salvar_impressora(filial_id: int, dados: ImpressoraUpdate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    filial = await unidade(filial_id, db)
    filial.ip_impressora = dados.ip_impressora
    await db.commit()
    await db.refresh(filial)
    return filial


def conectar_impressora(ip: str) -> None:
    with socket.create_connection((ip, 9100), timeout=3):
        pass  # Testa a conexão sem enviar uma impressão.


@router.post("/filiais/{filial_id}/impressora/testar")
async def testar_impressora(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    filial = await unidade(filial_id, db)
    if not filial.ip_impressora:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cadastre a impressora desta unidade antes de testar")
    try:
        await asyncio.to_thread(conectar_impressora, filial.ip_impressora)
    except OSError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Não foi possível conectar à impressora na porta 9100")
    return {"conectada": True, "mensagem": "Conexão com a impressora confirmada na porta 9100"}


@router.get("/filiais/{filial_id}/etiquetas", response_model=ImpressoraEtiquetaOut)
async def obter_impressora_etiquetas(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(filial_id, db)
    return await db.get(ImpressoraEtiqueta, filial_id) or ImpressoraEtiquetaOut(filial_id=filial_id)


@router.patch("/filiais/{filial_id}/etiquetas", response_model=ImpressoraEtiquetaOut)
async def salvar_impressora_etiquetas(filial_id: int, dados: ImpressoraEtiquetaUpdate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(filial_id, db)
    impressora = await db.get(ImpressoraEtiqueta, filial_id)
    if impressora is None:
        impressora = ImpressoraEtiqueta(filial_id=filial_id)
        db.add(impressora)
    for chave, valor in dados.model_dump().items():
        setattr(impressora, chave, valor)
    await db.commit()
    await db.refresh(impressora)
    return impressora


def conectar_etiquetas(ip, porta):
    with socket.create_connection((ip, porta), timeout=3):
        pass


@router.post("/filiais/{filial_id}/etiquetas/testar")
async def testar_impressora_etiquetas(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(filial_id, db)
    impressora = await db.get(ImpressoraEtiqueta, filial_id)
    if not impressora or not impressora.ip:
        raise HTTPException(400, "Cadastre o IP da impressora de etiquetas antes de testar")
    try:
        await asyncio.to_thread(conectar_etiquetas, impressora.ip, impressora.porta)
    except OSError:
        raise HTTPException(502, "Não foi possível conectar à impressora de etiquetas na porta configurada") from None
    return {"conectada": True, "mensagem": "Conexão confirmada. O teste não envia etiquetas"}


def consulta_usuarios():
    return select(Usuario).options(selectinload(Usuario.perfil), selectinload(Usuario.filiais))


async def validar_credencial(dados: UsuarioCreate | UsuarioUpdate, db: AsyncSession):
    perfil = (await db.execute(select(Perfil).where(Perfil.nome == dados.perfil))).scalar_one_or_none()
    if perfil is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Perfil inválido")
    ids = set(dados.filial_ids)
    filiais = list((await db.execute(select(Filial).where(Filial.id.in_(ids)))).scalars().all()) if ids else []
    if len(filiais) != len(ids):
        raise HTTPException(422, "Uma das unidades selecionadas não existe")
    if dados.perfil != "ADMIN_TI" and not any(f.ativa for f in filiais):
        raise HTTPException(422, "Selecione pelo menos uma unidade ativa para este usuário")
    return perfil, filiais


# ─── Utilizadores ────────────────────────────────────────────────────────────
@router.get("/autenticacao-ad")
async def configuracao_ad(_: Usuario = Depends(ADMIN)):
    return situacao_ad()


@router.get("/usuarios", response_model=list[UsuarioOut])
async def listar_usuarios(db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    return (await db.execute(consulta_usuarios().order_by(Usuario.nome))).scalars().all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
async def criar_usuario(dados: UsuarioCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    existe = (await db.execute(select(Usuario).where(func.lower(Usuario.nome_usuario) == dados.nome_usuario))).scalar_one_or_none()
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nome de usuário já cadastrado")
    perfil, filiais = await validar_credencial(dados, db)
    local = dados.origem_autenticacao == "LOCAL"
    usuario = Usuario(nome=dados.nome, nome_usuario=dados.nome_usuario,
        senha_hash=hash_senha(dados.senha if local else secrets.token_urlsafe(32)),
        origem_autenticacao=dados.origem_autenticacao, usuario_ad=dados.usuario_ad,
        perfil=perfil, filiais=filiais, troca_senha_obrigatoria=local)
    db.add(usuario)
    await confirmar(db, "Nome de usuário ou conta AD já cadastrados")
    await db.refresh(usuario)
    return UsuarioOut.model_validate(usuario)


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioOut)
async def atualizar_usuario(usuario_id: int, dados: UsuarioUpdate, db: AsyncSession = Depends(get_db), administrador: Usuario = Depends(ADMIN)):
    usuario = (await db.execute(consulta_usuarios().where(Usuario.id == usuario_id).with_for_update(of=Usuario))).scalar_one_or_none()
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    if usuario.id == administrador.id and (not dados.ativo or dados.perfil != "ADMIN_TI"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode desativar ou retirar o perfil administrativo da sua própria conta")
    if usuario.id == administrador.id and dados.senha is not None:
        raise HTTPException(422, "Use a opção Alterar minha senha para mudar a senha da própria conta")
    mudou_vinculo = usuario.origem_autenticacao != dados.origem_autenticacao or usuario.usuario_ad != dados.usuario_ad
    if usuario.id == administrador.id and mudou_vinculo:
        raise HTTPException(409, "Outra conta administrativa deve alterar a origem de autenticação da sua conta")
    if usuario.ativo and usuario.perfil.nome == "ADMIN_TI" and usuario.origem_autenticacao == "LOCAL" and (
        not dados.ativo or dados.perfil != "ADMIN_TI" or dados.origem_autenticacao != "LOCAL"
    ):
        administradores = (await db.execute(
            select(Usuario).join(Usuario.perfil).where(Usuario.ativo.is_(True), Perfil.nome == "ADMIN_TI", Usuario.origem_autenticacao == "LOCAL")
            .order_by(Usuario.id).with_for_update(of=Usuario)
        )).scalars().all()
        if len(administradores) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Mantenha pelo menos um administrador local ativo")
    if usuario.origem_autenticacao == "AD" and dados.origem_autenticacao == "LOCAL" and dados.senha is None:
        raise HTTPException(422, "Defina uma senha temporária ao converter a conta AD em conta local")
    perfil, filiais = await validar_credencial(dados, db)
    usuario.nome, usuario.nome_usuario = dados.nome, dados.nome_usuario
    usuario.perfil, usuario.filiais, usuario.ativo = perfil, filiais, dados.ativo
    usuario.origem_autenticacao, usuario.usuario_ad = dados.origem_autenticacao, dados.usuario_ad
    if mudou_vinculo:
        usuario.ad_object_guid = None
    if dados.origem_autenticacao == "AD":
        usuario.troca_senha_obrigatoria = False
        if mudou_vinculo:
            usuario.senha_hash = hash_senha(secrets.token_urlsafe(32))
    elif dados.senha is not None:
        usuario.senha_hash = hash_senha(dados.senha)
        usuario.troca_senha_obrigatoria = True
    if mudou_vinculo or dados.senha is not None or not dados.ativo:
        await revogar_sessoes(db, usuario.id)
    await confirmar(db, "Nome de usuário ou conta AD já cadastrados")
    await db.refresh(usuario)
    await gerenciador_ws.encerrar_usuario(usuario.id)
    return UsuarioOut.model_validate(usuario)
