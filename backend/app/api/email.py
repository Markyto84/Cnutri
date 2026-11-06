"""Configuração e acompanhamento por unidade, exclusivos da administração de TI."""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ..core.config import settings
from ..core.database import get_db
from ..core.presenca import agora_utc
from ..core.security import exigir_perfis
from ..models.models import AvisoEmailPedido, ConfiguracaoEmailUnidade, Filial, Pedido, Usuario
from ..schemas.email import ConfiguracaoEmailUpdate, ReenvioEmail
from ..services.auditoria import registrar
from ..services.email_medico import ErroEnvioEmail, cifrar_senha, obter_conexao, parametros_smtp, transportar_email
from ..services.operacao import data_utc

router = APIRouter(prefix="/api/admin/avisos-email", tags=["Avisos por e-mail"])
ADMIN = exigir_perfis("ADMIN_TI")
CAMPOS_SMTP = ("servidor", "porta", "seguranca", "autenticar", "usuario", "servidor_secundario", "porta_secundaria", "tempo_limite", "endereco_resposta")


def acesso_seguro(request):
    endereco = request.headers.get("origin") or f'{request.url.scheme}://{request.headers.get("x-forwarded-host") or request.url.netloc}'
    origem = urlsplit(endereco)
    return origem.scheme == "https" or origem.hostname in ("localhost", "127.0.0.1", "::1")


async def unidade(db, filial_id, bloquear=False):
    filial = await db.scalar(select(Filial).where(Filial.id == filial_id).with_for_update()) if bloquear else await db.get(Filial, filial_id)
    if filial is None:
        raise HTTPException(404, "Unidade não encontrada")
    return filial


def retrato(config):
    return {**{c: getattr(config, c) for c in ("modo", "remetente", "habilitado")}, **parametros_smtp(config)} if config else None


def resposta(config, request):
    return {"modo": config.modo if config else "SMTP", "remetente": config.remetente if config else "",
        "habilitado": config.habilitado if config else False, "senha_configurada": bool(config and config.senha_cifrada),
        "protecao_preparada": bool(settings.EMAIL_CREDENCIAIS_CHAVE), "acesso_seguro": acesso_seguro(request),
        **(parametros_smtp(config) if config else {"servidor": "", "porta": 587, "seguranca": "STARTTLS", "autenticar": True, "usuario": "",
            "servidor_secundario": None, "porta_secundaria": None, "tempo_limite": 30, "endereco_resposta": None})}


@router.get("/{filial_id}/configuracao")
async def consultar(filial_id: int, request: Request, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(db, filial_id)
    config = await db.scalar(select(ConfiguracaoEmailUnidade).options(undefer(ConfiguracaoEmailUnidade.senha_cifrada))
        .where(ConfiguracaoEmailUnidade.filial_id == filial_id))
    return resposta(config, request)


@router.put("/{filial_id}/configuracao")
async def salvar(filial_id: int, dados: ConfiguracaoEmailUpdate, request: Request, db: AsyncSession = Depends(get_db), autor: Usuario = Depends(ADMIN)):
    await unidade(db, filial_id, bloquear=True)
    config = await db.scalar(select(ConfiguracaoEmailUnidade).options(undefer(ConfiguracaoEmailUnidade.senha_cifrada))
        .where(ConfiguracaoEmailUnidade.filial_id == filial_id))
    antes = retrato(config)
    if dados.senha_app and not acesso_seguro(request):
        raise HTTPException(400, "Para cadastrar a credencial de e-mail, use HTTPS ou acesse pelo endereço local no próprio servidor")
    if config is None:
        config = ConfiguracaoEmailUnidade(filial_id=filial_id, modo=dados.modo, remetente=dados.remetente,
            habilitado=False, senha_cifrada=None)
        db.add(config)
    parametros_antes = parametros_smtp(config)
    trocou_conta = config.modo != dados.modo or any(parametros_antes[c] != getattr(dados, c) for c in ("servidor", "usuario", "autenticar"))
    if dados.senha_app and dados.modo == "GOOGLE_RELAY":
        raise HTTPException(422, "O relay por IP é autorizado no Google Workspace pela TI e dispensa senha de app")
    if not dados.autenticar or trocou_conta:
        config.senha_cifrada = None
    if dados.senha_app:
        config.senha_cifrada = cifrar_senha(filial_id, dados.senha_app.get_secret_value())
    if dados.habilitado and dados.autenticar and not config.senha_cifrada:
        raise HTTPException(422, "Cadastre a credencial da conta desta unidade antes de ativar os avisos")
    config.modo, config.remetente, config.habilitado = dados.modo, dados.remetente, dados.habilitado
    for campo in CAMPOS_SMTP:
        setattr(config, campo, getattr(dados, campo))
    depois = retrato(config)
    if dados.senha_app:
        depois = {**depois, "credencial_atualizada": True}
    registrar(db, autor, "EMAIL_UNIDADE", filial_id, filial_id, antes, depois)
    await db.commit()
    return resposta(config, request)


@router.post("/{filial_id}/testar")
async def testar(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(db, filial_id)
    conexao = await obter_conexao(db, filial_id, exigir_habilitado=False)
    try:
        resultado = await run_in_threadpool(transportar_email, conexao)
    except ErroEnvioEmail as exc:
        raise HTTPException(502, exc.mensagem) from None
    return {"mensagem": "Conexão SMTP verificada. Nenhuma mensagem de teste foi enviada",
        "servidor_verificado": resultado if isinstance(resultado, dict) else None,
        "observacao": "A autorização do remetente e do destinatário no relay será conferida durante um envio real" if not conexao.autenticar else None}


@router.get("/{filial_id}/avisos")
async def avisos(filial_id: int, pagina: int = Query(1, ge=1), db: AsyncSession = Depends(get_db), _: Usuario = Depends(ADMIN)):
    await unidade(db, filial_id)
    consulta = select(AvisoEmailPedido).where(AvisoEmailPedido.filial_id == filial_id)
    linhas = (await db.scalars(consulta.order_by(AvisoEmailPedido.id.desc()).offset((pagina - 1) * 20).limit(20))).all()
    total = await db.scalar(select(func.count()).select_from(AvisoEmailPedido).where(AvisoEmailPedido.filial_id == filial_id))
    return {"total": total, "itens": [{"id": a.id, "pedido_id": a.pedido_id, "destinatario": a.destinatario,
        "estado": a.estado, "tentativas": a.tentativas, "erro": a.erro, "criado_em": data_utc(a.criado_em),
        "enviado_em": data_utc(a.enviado_em)} for a in linhas]}


@router.post("/{filial_id}/avisos/{aviso_id}/reenviar")
async def reenviar(filial_id: int, aviso_id: int, dados: ReenvioEmail, db: AsyncSession = Depends(get_db), autor: Usuario = Depends(ADMIN)):
    await unidade(db, filial_id)
    # Mesma ordem de bloqueios das operações do pedido: pedido antes do aviso.
    pedido_id = await db.scalar(select(AvisoEmailPedido.pedido_id).where(AvisoEmailPedido.id == aviso_id, AvisoEmailPedido.filial_id == filial_id))
    if pedido_id is None:
        raise HTTPException(404, "Aviso não encontrado nesta unidade")
    pedido = await db.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update())
    aviso = await db.scalar(select(AvisoEmailPedido).where(AvisoEmailPedido.id == aviso_id).with_for_update())
    if aviso.estado not in ("FALHA", "INCERTO", "DESATIVADO"):
        raise HTTPException(409, "Este aviso já foi enviado, está na fila ou não pode mais ser enviado")
    if aviso.estado == "INCERTO" and not dados.confirmar_risco_duplicidade:
        raise HTTPException(409, "O envio anterior pode ter sido aceito. Confira o recebimento antes de confirmar o reenvio")
    if pedido.status != "PRONTO" or pedido.versao != aviso.versao or aviso.expira_em <= agora_utc():
        raise HTTPException(409, "O pedido mudou ou o prazo de 30 minutos para avisar a saída foi encerrado")
    await obter_conexao(db, filial_id)
    anterior = aviso.estado
    aviso.estado, aviso.erro, aviso.reserva, aviso.tentativas = "PENDENTE", None, None, 0
    aviso.proxima_tentativa_em = agora_utc()
    registrar(db, autor, "AVISO_EMAIL", aviso.id, filial_id, {"estado": anterior}, {"estado": "PENDENTE"}, "REENVIAR")
    await db.commit()
    return {"mensagem": "Aviso colocado novamente na fila"}
