"""Rotas públicas do modo Kiosk (postos de enfermagem/médico, sem login).

A filial é identificada pelo slug na URL. A rastreabilidade é feita pelo
registro profissional informado no envio da solicitação.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from hashlib import sha256
import json
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.ws import gerenciador_ws
from ..models.models import Dieta, Filial, FormularioConfig, Pedido
from ..schemas.schemas import PedidoCreate, PedidoOut
from ..services.fila_impressao import enfileirar
from ..services.validacao_pedidos import validar_pedido

router = APIRouter(prefix="/api/public", tags=["Kiosk Público"])


async def obter_filial(slug: str, db: AsyncSession) -> Filial:
    resultado = await db.execute(
        select(Filial).where(Filial.codigo_slug == slug, Filial.ativa == True)  # noqa: E712
    )
    filial = resultado.scalar_one_or_none()
    if filial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unidade '{slug}' não encontrada")
    return filial


@router.get("/{slug}/config")
async def obter_config_kiosk(slug: str, db: AsyncSession = Depends(get_db)):
    """Devolve o nome da filial, o catálogo de dietas e os formulários dinâmicos dos dois fluxos."""
    filial = await obter_filial(slug, db)
    dietas = (
        await db.execute(
            select(Dieta).where(Dieta.filial_id == filial.id, Dieta.ativa == True).order_by(Dieta.nome)  # noqa: E712
        )
    ).scalars().all()
    configs = (
        await db.execute(select(FormularioConfig).where(FormularioConfig.filial_id == filial.id))
    ).scalars().all()

    esquemas = {c.tipo_publico: c.esquema_json for c in configs}
    return {
        "filial": {"id": filial.id, "nome": filial.nome, "codigo_slug": filial.codigo_slug},
        "dietas": [{"id": d.id, "nome": d.nome, "severa": d.severa} for d in dietas],
        "formularios": esquemas,
    }


@router.post("/{slug}/pedidos", response_model=PedidoOut, status_code=status.HTTP_201_CREATED)
async def criar_pedido(slug: str, dados: PedidoCreate, request: Request, response: Response,
    chave: UUID | None = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db)):
    filial = await obter_filial(slug, db)
    filial_id = filial.id

    chave = str(chave or uuid4())
    resumo = sha256(json.dumps(dados.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    existente = await buscar_envio(db, filial.id, chave)
    if existente:
        return conferir_repeticao(existente, resumo, response)
    await validar_pedido(db, filial.id, dados)

    pedido = Pedido(
        filial_id=filial.id,
        tipo_solicitacao=dados.tipo_solicitacao,
        solicitante_identificacao=dados.solicitante_identificacao.strip(),
        solicitante_nome=dados.solicitante_nome,
        leito=dados.leito,
        prontuario=dados.prontuario,
        nome_paciente=dados.nome_paciente,
        dieta_id=dados.dieta_id,
        observacoes_alergias=dados.observacoes_alergias,
        dados_dinamicos=dados.dados_dinamicos,
        ip_origem=request.client.host if request.client else None,
        status="PENDENTE", chave_envio=chave, hash_envio=resumo,
    )
    db.add(pedido)
    try:
        await db.flush()
        await enfileirar(db, pedido, filial)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existente = await buscar_envio(db, filial_id, chave)
        if existente:
            return conferir_repeticao(existente, resumo, response)
        raise
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=["dieta", "trabalhos_impressao"])
    # A fila é processada fora da requisição; pedido e trabalho são gravados juntos.
    await gerenciador_ws.transmitir(
        filial.id,
        {"evento": "novo_pedido", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json")},
    )
    return pedido


async def buscar_envio(db, filial_id, chave):
    return await db.scalar(select(Pedido).options(selectinload(Pedido.dieta)).where(Pedido.filial_id == filial_id, Pedido.chave_envio == chave))


def conferir_repeticao(pedido, resumo, response):
    if pedido.hash_envio != resumo:
        raise HTTPException(409, jsonable_encoder({"mensagem": "A solicitação anterior já foi registrada. Os novos dados não foram enviados", "pedido_id": pedido.id, "impressao": pedido.impressao}))
    response.status_code = 200
    return pedido


@router.get("/{slug}/solicitacoes/{chave}")
async def consultar_envio(slug: str, chave: UUID, db: AsyncSession = Depends(get_db)):
    filial = await obter_filial(slug, db)
    pedido = await buscar_envio(db, filial.id, str(chave))
    if not pedido:
        raise HTTPException(404, "Solicitação ainda não localizada")
    # O comprovante aleatório dá acesso só ao número e ao estado de impressão.
    return {"id": pedido.id, "impressao": pedido.impressao}
