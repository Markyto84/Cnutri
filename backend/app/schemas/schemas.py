"""Schemas Pydantic de validação de entrada/saída."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TipoPublico = Literal["MEDICO", "ENFERMAGEM"]
TipoSolicitacao = Literal["MEDICO", "PACIENTE"]
StatusPedido = Literal["PENDENTE", "EM_PREPARO", "PRONTO", "CANCELADO"]


# ─── Autenticação ────────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    perfil: str
    nome: str


# ─── Filiais ─────────────────────────────────────────────────────────────────
class FilialCreate(BaseModel):
    nome: str = Field(max_length=100)
    codigo_slug: str = Field(max_length=50, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    ip_impressora: str | None = None


class FilialOut(FilialCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ativa: bool


# ─── Usuários ────────────────────────────────────────────────────────────────
class UsuarioCreate(BaseModel):
    nome: str = Field(max_length=100)
    email: str = Field(max_length=120)
    senha: str = Field(min_length=6)
    perfil: Literal["ADMIN_TI", "NUTRICIONISTA", "COZINHA"]
    filial_ids: list[int] = []


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
    ativo: bool
    perfil: str
    filiais: list[FilialOut]


# ─── Dietas ──────────────────────────────────────────────────────────────────
class DietaCreate(BaseModel):
    nome: str = Field(max_length=100)
    descricao: str | None = None
    severa: bool = False


class DietaOut(DietaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filial_id: int
    ativa: bool


# ─── Formulários dinâmicos ───────────────────────────────────────────────────
class FormularioConfigOut(BaseModel):
    id: int
    filial_id: int
    tipo_publico: str
    esquema_json: dict[str, Any]
    atualizado_em: datetime


class FormularioConfigUpdate(BaseModel):
    esquema_json: dict[str, Any]
    versao: str | None = None  # timestamp da configuração carregada — proteção contra edição concorrente


# ─── Pedidos ─────────────────────────────────────────────────────────────────
class PedidoCreate(BaseModel):
    tipo_solicitacao: TipoSolicitacao
    solicitante_identificacao: str = Field(max_length=50, description="CRM, COREN ou Matrícula")
    solicitante_nome: str | None = Field(default=None, max_length=100)
    leito: str | None = Field(default=None, max_length=30)
    prontuario: str | None = Field(default=None, max_length=50)
    nome_paciente: str | None = Field(default=None, max_length=100)
    dieta_id: int | None = None
    observacoes_alergias: str | None = None
    dados_dinamicos: dict[str, Any] = {}


class PedidoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filial_id: int
    tipo_solicitacao: str
    solicitante_identificacao: str
    solicitante_nome: str | None
    leito: str | None
    prontuario: str | None
    nome_paciente: str | None
    dieta_id: int | None
    dieta: DietaOut | None
    observacoes_alergias: str | None
    dados_dinamicos: dict[str, Any]
    status: str
    criado_em: datetime
    concluido_em: datetime | None


class StatusUpdate(BaseModel):
    status: StatusPedido


# ─── Relatórios ──────────────────────────────────────────────────────────────
class RelatorioSLAOut(BaseModel):
    total_concluidos: int
    sla_medio_minutos: float | None


class RelatorioConsumoItem(BaseModel):
    turno: str
    solicitante: str
    total: int


class RelatorioDietasItem(BaseModel):
    dieta: str
    setor: str | None = None
    total: int