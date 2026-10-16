"""Rotas públicas do modo Kiosk (postos de enfermagem/médico, sem login).

A filial é identificada pelo slug na URL. A rastreabilidade é feita pelo
registro profissional informado no envio da solicitação.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.ws import gerenciador_ws
from ..models.models import Dieta, Filial, FormularioConfig, Pedido
from ..schemas.schemas import PedidoCreate, PedidoOut
from ..services.impressora import imprimir_filipeta, montar_filipeta

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
async def criar_pedido(slug: str, dados: PedidoCreate, request: Request, db: AsyncSession = Depends(get_db)):
    filial = await obter_filial(slug, db)

    if dados.dieta_id is not None:
        dieta = await db.get(Dieta, dados.dieta_id)
        if dieta is None or dieta.filial_id != filial.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dieta inválida para esta unidade")
    if dados.tipo_solicitacao == "PACIENTE" and not dados.nome_paciente:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nome do paciente é obrigatório")

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
        status="PENDENTE",
    )
    db.add(pedido)
    await db.commit()
    await db.refresh(pedido)

    # Impressão silenciosa da filipeta (não bloqueia o fluxo em caso de falha)
    dieta_nome = dieta.nome if dados.dieta_id is not None else None
    severa = bool(dieta.severa) if dados.dieta_id is not None else False
    if filial.ip_impressora:
        buffer = montar_filipeta(
            pedido_id=pedido.id,
            filial_nome=filial.nome,
            tipo_solicitacao=pedido.tipo_solicitacao,
            paciente_ou_solicitante=pedido.nome_paciente or pedido.solicitante_nome or "-",
            leito=pedido.leito,
            dieta_nome=dieta_nome,
            observacoes=pedido.observacoes_alergias,
            severa=severa,
            andar=pedido.dados_dinamicos.get("andar"),
            refeicao=pedido.dados_dinamicos.get("refeicao"),
            para=pedido.dados_dinamicos.get("para"),
            espessado=pedido.dados_dinamicos.get("liquido_espessado"),
        )
        imprimir_filipeta(filial.ip_impressora, buffer)

    await gerenciador_ws.transmitir(
        filial.id,
        {"evento": "novo_pedido", "pedido": PedidoOut.model_validate(pedido).model_dump(mode="json")},
    )
    return pedido