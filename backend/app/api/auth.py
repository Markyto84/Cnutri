"""Autenticação: nome de usuário definido pela TI e senha (JWT)."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, filiais_permitidas, get_current_user, hash_senha, oauth2_scheme, verificar_acesso_filial, verificar_senha
from ..core.config import settings
from ..core.presenca import TEMPO_PRESENCA, agora_utc
from ..core.login_usuarios import normalizar_usuario
from ..core.controle_login import conferir_limites, logger
from ..core.sessoes import emitir_sessao, revogar_sessoes
from ..services.active_directory import ADIndisponivel, autenticar_ad
from ..models.models import SessaoCopeira, SessaoUsuario, Usuario
from ..schemas.schemas import FilialOut, PresencaUpdate, TokenResponse, TrocaSenhaCreate, UsuarioOut

HASH_COMPARACAO = hash_senha("ComparacaoDeCredencial@2026")

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    nome_usuario = normalizar_usuario(form.username)[:120]
    ip = request.client.host if request.client else "desconhecido"
    limites = await conferir_limites(db, ip, nome_usuario)
    resultado = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfil)).where(
            func.lower(Usuario.nome_usuario) == nome_usuario
        ).with_for_update(of=Usuario)
    )
    usuario = resultado.scalar_one_or_none()
    correta = False
    if usuario and usuario.ativo and usuario.origem_autenticacao == "AD":
        if not settings.AD_HABILITADO:
            raise HTTPException(503, "Integração com o Active Directory desativada. Procure a TI.")
        if request.url.scheme != "https":
            raise HTTPException(503, "O acesso pelo Active Directory exige HTTPS no Cnutri. Procure a TI.")
        try:
            guid = await asyncio.to_thread(autenticar_ad, usuario.usuario_ad, form.password)
        except ADIndisponivel:
            for limite in limites:
                limite.falhas += 1
            await db.commit()
            logger.warning("ad_indisponivel usuario_id=%s", usuario.id)
            raise HTTPException(503, "Active Directory indisponível. Procure a TI ou tente novamente mais tarde.") from None
        if guid and (not usuario.ad_object_guid or usuario.ad_object_guid == guid):
            outra_conta = await db.scalar(select(Usuario.id).where(Usuario.ad_object_guid == guid, Usuario.id != usuario.id))
            if outra_conta is None:
                usuario.ad_object_guid = guid
                try:
                    await db.flush()
                except IntegrityError:
                    await db.rollback()
                    raise HTTPException(401, "Usuário ou senha inválidos") from None
                correta = True
    else:
        correta = verificar_senha(form.password, usuario.senha_hash if usuario and usuario.origem_autenticacao == "LOCAL" else HASH_COMPARACAO)
    if usuario is None or not correta or not usuario.ativo:
        for limite in limites:
            limite.falhas += 1
        await db.commit()
        logger.warning("login_falhou ip=%s usuario_id=%s", ip, usuario.id if usuario else "nao_identificado")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha inválidos")
    limites[1].falhas = 0  # limite por usuário/IP; o limite geral do IP mantém as falhas.
    resposta = await emitir_sessao(db, usuario)
    logger.info("login_sucesso ip=%s usuario_id=%s", ip, usuario.id)
    return resposta


@router.post("/senha", response_model=TokenResponse)
async def trocar_senha(dados: TrocaSenhaCreate, request: Request, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if usuario.origem_autenticacao == "AD":
        raise HTTPException(403, "A senha desta conta é administrada pelo Active Directory. Solicite a alteração à TI.")
    ip = request.client.host if request.client else "desconhecido"
    limites = await conferir_limites(db, ip, f"senha:{usuario.id}")
    # Uma redefinição concorrente deve prevalecer sobre a senha carregada no início da requisição.
    await db.refresh(usuario, attribute_names=["senha_hash", "troca_senha_obrigatoria"], with_for_update={"of": Usuario})
    if not verificar_senha(dados.senha_atual, usuario.senha_hash):
        for limite in limites:
            limite.falhas += 1
        await db.commit()
        logger.warning("troca_senha_falhou ip=%s usuario_id=%s", ip, usuario.id)
        raise HTTPException(400, "A senha atual está incorreta")
    if verificar_senha(dados.nova_senha, usuario.senha_hash):
        raise HTTPException(422, "Escolha uma senha diferente da atual")
    usuario.senha_hash = hash_senha(dados.nova_senha)
    limites[1].falhas = 0
    usuario.troca_senha_obrigatoria = False
    await revogar_sessoes(db, usuario.id)
    from ..services.auditoria import registrar
    registrar(db, usuario, "CREDENCIAL", usuario.id, None, None, {"senha_alterada": True}, "TROCAR_SENHA")
    resposta = await emitir_sessao(db, usuario)
    from ..core.ws import gerenciador_ws
    await gerenciador_ws.encerrar_usuario(usuario.id)
    logger.info("senha_alterada usuario_id=%s", usuario.id)
    return resposta


@router.get("/me", response_model=UsuarioOut)
async def perfil_atual(db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    dados = UsuarioOut.model_validate(usuario)
    return dados.model_copy(update={"filiais": [FilialOut.model_validate(f) for f in await filiais_permitidas(usuario, db)]})


@router.post("/presenca")
async def atualizar_presenca(dados: PresencaUpdate, token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(exigir_perfis("COPEIRA"))):
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
    sessao = await db.get(SessaoUsuario, payload["jti"])
    sessao.encerrada_em = agora_utc()
    presenca = await db.get(SessaoCopeira, payload["jti"])
    if presenca:
        presenca.encerrada_em = agora_utc()
    await db.commit()
    from ..core.ws import gerenciador_ws
    await gerenciador_ws.encerrar_usuario(usuario.id)
    return {"saiu": True}
