"""Central de impressão, alertas por unidade e histórico administrativo autorizado."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import AuditoriaAdministrativa, ConfiguracaoOperacional, Filial, Pedido, TrabalhoImpressao, Usuario
from ..schemas.schemas import AlertasUpdate, ReimpressaoCreate
from ..services.auditoria import registrar, retrato
from ..services.fila_impressao import enfileirar, resposta_fila
from ..services.operacao import data_utc
from .operacao import notificar, unidade_ativa

router = APIRouter(prefix="/api", tags=["Melhorias operacionais"])
GESTAO = exigir_perfis("NUTRICIONISTA", "ADMIN_TI")
OPERACAO = exigir_perfis("COZINHA", "NUTRICIONISTA", "ADMIN_TI")
ESTADOS = Literal["PENDENTE", "PROCESSANDO", "ENVIADO", "FALHA", "INCERTO", "CANCELADO"]
ENTIDADES = Literal["UNIDADE", "CREDENCIAL", "DIETA", "FORMULARIO", "IMPRESSORA_FILIPETA", "IMPRESSORA_ETIQUETA", "ALERTAS"]
BRASILIA = timezone(timedelta(hours=-3))


def periodo(inicio, fim):
    hoje = datetime.now(BRASILIA).date()
    inicio, fim = inicio or hoje - timedelta(days=6), fim or hoje
    if inicio > fim or (fim - inicio).days > 90:
        raise HTTPException(422, "Informe um período de até 91 dias, com início anterior ou igual ao fim")
    def utc(dia):
        return datetime.combine(dia, time.min, BRASILIA).astimezone(timezone.utc).replace(tzinfo=None)
    try:
        return utc(inicio), utc(fim + timedelta(days=1))
    except (OverflowError, ValueError):
        raise HTTPException(422, "Período fora do intervalo de datas permitido") from None


async def limitar_unidade(filial_id, usuario, db, coluna):
    if filial_id is not None:
        await verificar_acesso_filial(filial_id, usuario, db)
        return coluna == filial_id
    if usuario.perfil.nome == "ADMIN_TI":
        return True
    return coluna.in_([f.id for f in usuario.filiais if f.ativa])


def limites(config):
    return {campo: getattr(config, campo) if config is not None else 30 for campo in ("preparo_minutos", "entrega_minutos")}


@router.get("/operacao/unidades/{filial_id}/alertas")
async def alertas_publicos(filial_id: int, db: AsyncSession = Depends(get_db)):
    await unidade_ativa(filial_id, db)
    return limites(await db.get(ConfiguracaoOperacional, filial_id))


@router.get("/gestao/alertas/{filial_id}")
async def obter_alertas(filial_id: int, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTAO)):
    await verificar_acesso_filial(filial_id, usuario, db)
    return limites(await db.get(ConfiguracaoOperacional, filial_id))


@router.put("/gestao/alertas/{filial_id}")
async def salvar_alertas(filial_id: int, dados: AlertasUpdate, db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTAO)):
    await verificar_acesso_filial(filial_id, usuario, db)
    await db.scalar(select(Filial.id).where(Filial.id == filial_id).with_for_update())
    config = await db.get(ConfiguracaoOperacional, filial_id)
    antes = limites(config)
    if config is None:
        config = ConfiguracaoOperacional(filial_id=filial_id)
        db.add(config)
    config.preparo_minutos, config.entrega_minutos = dados.preparo_minutos, dados.entrega_minutos
    registrar(db, usuario, "ALERTAS", filial_id, filial_id, antes, limites(config))
    await db.commit()
    return limites(config)


@router.get("/impressoes")
async def listar_impressoes(response: Response, filial_id: int | None = Query(None, gt=0),
    estado: ESTADOS | None = None, tipo: Literal["FILIPETA", "ETIQUETA"] | None = None,
    pedido_id: int | None = Query(None, gt=0), inicio: date | None = None, fim: date | None = None,
    pagina: int = Query(1, ge=1, le=1000000), tamanho: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(OPERACAO)):
    response.headers["Cache-Control"] = "private, no-store"
    de, ate = periodo(inicio, fim)
    condicoes = [await limitar_unidade(filial_id, usuario, db, Pedido.filial_id),
                  TrabalhoImpressao.criado_em >= de, TrabalhoImpressao.criado_em < ate]
    if estado:
        condicoes.append(TrabalhoImpressao.estado == estado)
    if tipo:
        condicoes.append(TrabalhoImpressao.tipo_documento == tipo)
    if pedido_id:
        condicoes.append(TrabalhoImpressao.pedido_id == pedido_id)
    total = await db.scalar(select(func.count()).select_from(TrabalhoImpressao).join(Pedido).where(*condicoes))
    # Colunas explícitas evitam carregar documentos, configurações e dados de paciente.
    consulta = select(TrabalhoImpressao.id, TrabalhoImpressao.pedido_id, TrabalhoImpressao.tipo_documento,
        TrabalhoImpressao.estado, TrabalhoImpressao.tentativas, TrabalhoImpressao.erro,
        TrabalhoImpressao.criado_em, TrabalhoImpressao.enviado_em, TrabalhoImpressao.proxima_tentativa_em,
        Pedido.filial_id, Pedido.status.label("pedido_status"), Filial.nome.label("unidade"), Filial.ativa.label("unidade_ativa"))
    linhas = (await db.execute(consulta.select_from(TrabalhoImpressao)
        .join(Pedido, Pedido.id == TrabalhoImpressao.pedido_id).join(Filial, Filial.id == Pedido.filial_id)
        .where(*condicoes).order_by(TrabalhoImpressao.id.desc()).offset((pagina - 1) * tamanho).limit(tamanho))).mappings().all()
    pares = {(l["pedido_id"], l["tipo_documento"]) for l in linhas}
    ultimos = {}
    if pares:
        ids = {p for p, _ in pares}
        ultimos = {(p, t): i for p, t, i in (await db.execute(select(TrabalhoImpressao.pedido_id,
            TrabalhoImpressao.tipo_documento, func.max(TrabalhoImpressao.id)).where(TrabalhoImpressao.pedido_id.in_(ids))
            .group_by(TrabalhoImpressao.pedido_id, TrabalhoImpressao.tipo_documento))).all()}
    itens = []
    for linha in linhas:
        item = dict(linha)
        item["pode_reenviar"] = bool(item["unidade_ativa"] and item["estado"] in ("FALHA", "INCERTO")
            and item["pedido_status"] in ("PENDENTE", "EM_PREPARO", "PRONTO")
            and (item["tipo_documento"] != "ETIQUETA" or item["pedido_status"] == "PRONTO")
            and ultimos.get((item["pedido_id"], item["tipo_documento"])) == item["id"])
        for campo in ("criado_em", "enviado_em", "proxima_tentativa_em"):
            item[campo] = data_utc(item[campo])
        itens.append(item)
    return {"itens": itens, "total": total, "pagina": pagina, "tamanho": tamanho}


@router.post("/impressoes/{trabalho_id}/reenviar", status_code=202)
async def reenviar_impressao(trabalho_id: int, dados: ReimpressaoCreate,
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(OPERACAO)):
    job = await db.get(TrabalhoImpressao, trabalho_id)
    if job is None:
        raise HTTPException(404, "Trabalho de impressão não encontrado")
    pedido = await db.scalar(select(Pedido).options(selectinload(Pedido.dieta))
        .where(Pedido.id == job.pedido_id).with_for_update(of=Pedido))
    filial = await verificar_acesso_filial(pedido.filial_id, usuario, db)
    await db.refresh(job)
    if not filial.ativa or pedido.status not in ("PENDENTE", "EM_PREPARO", "PRONTO"):
        raise HTTPException(409, "Este pedido não está mais em operação")
    ultimo = await db.scalar(select(TrabalhoImpressao.id).where(TrabalhoImpressao.pedido_id == pedido.id,
        TrabalhoImpressao.tipo_documento == job.tipo_documento).order_by(TrabalhoImpressao.id.desc()).limit(1))
    if ultimo != job.id or job.estado not in ("FALHA", "INCERTO"):
        raise HTTPException(409, "A impressão já foi atualizada. Atualize a central antes de reenviar")
    novo = await enfileirar(db, pedido, filial, usuario.id, dados.confirmar_risco_duplicidade, job.tipo_documento)
    await db.commit()
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    await notificar(pedido)
    return resposta_fila(novo)


@router.get("/gestao/auditoria")
async def listar_auditoria(response: Response, filial_id: int | None = Query(None, gt=0), entidade: ENTIDADES | None = None,
    inicio: date | None = None, fim: date | None = None, pagina: int = Query(1, ge=1, le=1000000),
    tamanho: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(GESTAO)):
    response.headers["Cache-Control"] = "private, no-store"
    de, ate = periodo(inicio, fim)
    condicoes = [await limitar_unidade(filial_id, usuario, db, AuditoriaAdministrativa.filial_id),
                  AuditoriaAdministrativa.criado_em >= de, AuditoriaAdministrativa.criado_em < ate]
    if entidade:
        condicoes.append(AuditoriaAdministrativa.entidade == entidade)
    # Credenciais são globais e visíveis exclusivamente à TI, mesmo que seja incluído filial_id no futuro.
    if usuario.perfil.nome != "ADMIN_TI":
        condicoes.append(AuditoriaAdministrativa.entidade != "CREDENCIAL")
    total = await db.scalar(select(func.count()).select_from(AuditoriaAdministrativa).where(*condicoes))
    linhas = (await db.scalars(select(AuditoriaAdministrativa).where(*condicoes)
        .order_by(AuditoriaAdministrativa.id.desc()).offset((pagina - 1) * tamanho).limit(tamanho))).all()
    return {"itens": [{**retrato(l, ("id", "autor_usuario_id", "autor_nome", "filial_id", "entidade", "entidade_id", "acao", "antes", "depois")),
                       "criado_em": data_utc(l.criado_em)} for l in linhas],
            "total": total, "pagina": pagina, "tamanho": tamanho}
