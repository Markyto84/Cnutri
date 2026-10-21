"""Gestão de Nutrição: catálogo de dietas e motor de formulários dinâmicos."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import Dieta, Filial, FormularioConfig, Usuario
from ..schemas.schemas import DietaCreate, DietaOut, FormularioConfigOut, FormularioConfigUpdate
from ..services.validacao_pedidos import validar_esquema

router = APIRouter(prefix="/api/gestao", tags=["Gestão de Nutrição"])
PERFIS_GESTAO = ("NUTRICIONISTA", "ADMIN_TI")

# Esquema padrão sugerido para novos formulários
ESQUEMA_PADRAO_ENFERMAGEM = {
    "titulo": "Solicitação de Refeição — Paciente",
    "cabecalho": "",  # texto informativo exibido no topo do kiosk (editável pela Nutrição)
    "campos": [
        {"id": "leito", "rotulo": "Leito", "tipo": "texto", "obrigatorio": True},
        {"id": "prontuario", "rotulo": "Prontuário", "tipo": "texto", "obrigatorio": False},
        {"id": "nome_paciente", "rotulo": "Nome do Paciente", "tipo": "texto", "obrigatorio": True},
        {"id": "dieta_id", "rotulo": "Tipo de Dieta", "tipo": "selecao_dietas", "obrigatorio": True},
        {"id": "observacoes_alergias", "rotulo": "Restrições / Alergias / Observações", "tipo": "texto_longo", "obrigatorio": False},
    ],
}
ESQUEMA_PADRAO_MEDICO = {
    "titulo": "Solicitação de Refeição — Profissional",
    "campos": [
        {"id": "dieta_id", "rotulo": "Refeição / Dieta", "tipo": "selecao_dietas", "obrigatorio": True},
        {"id": "observacoes_alergias", "rotulo": "Observações", "tipo": "texto_longo", "obrigatorio": False},
    ],
}


async def _filial(filial_id: int, db: AsyncSession) -> Filial:
    f = await db.get(Filial, filial_id)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filial não encontrada")
    return f


# ─── Dietas ──────────────────────────────────────────────────────────────────
@router.get("/dietas", response_model=list[DietaOut])
async def listar_dietas(filial_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    await _filial(filial_id, db)
    await verificar_acesso_filial(filial_id, _, db)
    dietas = (
        await db.execute(select(Dieta).where(Dieta.filial_id == filial_id).order_by(Dieta.nome))
    ).scalars().all()
    return dietas


@router.post("/dietas", response_model=DietaOut, status_code=status.HTTP_201_CREATED)
async def criar_dieta(filial_id: int, dados: DietaCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    await _filial(filial_id, db)
    await verificar_acesso_filial(filial_id, _, db)
    dieta = Dieta(filial_id=filial_id, **dados.model_dump())
    db.add(dieta)
    await db.commit()
    await db.refresh(dieta)
    return dieta


@router.patch("/dietas/{dieta_id}", response_model=DietaOut)
async def atualizar_dieta(dieta_id: int, dados: DietaCreate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    dieta = await db.get(Dieta, dieta_id)
    if dieta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dieta não encontrada")
    await verificar_acesso_filial(dieta.filial_id, _, db)
    for campo, valor in dados.model_dump().items():
        setattr(dieta, campo, valor)
    await db.commit()
    await db.refresh(dieta)
    return dieta


@router.delete("/dietas/{dieta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desativar_dieta(dieta_id: int, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    """Desativa (soft delete) para preservar o histórico de pedidos."""
    dieta = await db.get(Dieta, dieta_id)
    if dieta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dieta não encontrada")
    await verificar_acesso_filial(dieta.filial_id, _, db)
    dieta.ativa = False
    await db.commit()


# ─── Formulários dinâmicos ───────────────────────────────────────────────────
@router.get("/formularios/{filial_id}/{tipo}", response_model=FormularioConfigOut | None)
async def obter_formulario(filial_id: int, tipo: str, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    await _filial(filial_id, db)
    await verificar_acesso_filial(filial_id, _, db)
    config = (
        await db.execute(
            select(FormularioConfig).where(
                FormularioConfig.filial_id == filial_id, FormularioConfig.tipo_publico == tipo
            )
        )
    ).scalar_one_or_none()
    return config


@router.put("/formularios/{filial_id}/{tipo}", response_model=FormularioConfigOut)
async def salvar_formulario(filial_id: int, tipo: str, dados: FormularioConfigUpdate, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    validar_esquema(dados.esquema_json)
    if tipo not in ("MEDICO", "ENFERMAGEM"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo deve ser MEDICO ou ENFERMAGEM")
    await _filial(filial_id, db)
    await verificar_acesso_filial(filial_id, _, db)
    config = (
        await db.execute(
            select(FormularioConfig).where(
                FormularioConfig.filial_id == filial_id, FormularioConfig.tipo_publico == tipo
            )
        )
    ).scalar_one_or_none()
    if config is None:
        config = FormularioConfig(filial_id=filial_id, tipo_publico=tipo, esquema_json=dados.esquema_json)
        db.add(config)
    else:
        # Proteção contra edição concorrente: se a configuração mudou desde que foi carregada,
        # bloqueia a publicação com a versão antiga (evita perder campos)
        if (
            dados.versao
            and config.atualizado_em
            and config.atualizado_em.isoformat() != dados.versao
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Este formulário foi alterado por outra pessoa/sessão enquanto você editava. "
                "Recarregue a página (F5) para trazer a versão mais recente antes de publicar.",
            )
        config.esquema_json = dados.esquema_json
    await db.commit()
    await db.refresh(config)
    return config


@router.post("/formularios/{filial_id}/{tipo}/resetar", response_model=FormularioConfigOut)
async def resetar_formulario(filial_id: int, tipo: str, db: AsyncSession = Depends(get_db), _: Usuario = Depends(exigir_perfis(*PERFIS_GESTAO))):
    padroes = {"MEDICO": ESQUEMA_PADRAO_MEDICO, "ENFERMAGEM": ESQUEMA_PADRAO_ENFERMAGEM}
    if tipo not in padroes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo deve ser MEDICO ou ENFERMAGEM")
    return await salvar_formulario(filial_id, tipo, FormularioConfigUpdate(esquema_json=padroes[tipo]), db, _)
