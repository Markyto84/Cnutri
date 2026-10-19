"""Schemas Pydantic de validação de entrada/saída."""
from datetime import datetime
from ipaddress import ip_address
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TipoPublico = Literal["MEDICO", "ENFERMAGEM"]
TipoSolicitacao = Literal["MEDICO", "PACIENTE"]
StatusPedido = Literal["PENDENTE", "EM_PREPARO", "PRONTO", "CANCELADO"]


# ─── Filiais ─────────────────────────────────────────────────────────────────
class FilialBase(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    codigo_slug: str = Field(max_length=50, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    ip_impressora: str | None = None

    @field_validator("nome", "codigo_slug", mode="before")
    @classmethod
    def remover_espacos(cls, valor: str) -> str:
        return valor.strip()

    @field_validator("ip_impressora", mode="before")
    @classmethod
    def validar_ip(cls, valor: str | None) -> str | None:
        if not valor or not valor.strip():
            return None
        try:
            return str(ip_address(valor.strip()))
        except ValueError:
            raise ValueError("Informe um endereço IP válido para a impressora")


class FilialCreate(FilialBase):
    origem_filial_id: int | None = Field(default=None, gt=0)


class FilialUpdate(FilialBase):
    ativa: bool = True


class FilialOut(FilialBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ativa: bool


# ─── Usuários ────────────────────────────────────────────────────────────────
class UsuarioBase(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=120, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    perfil: Literal["ADMIN_TI", "NUTRICIONISTA", "COZINHA"]
    filial_ids: list[int] = Field(default_factory=list)

    @field_validator("nome", "email", mode="before")
    @classmethod
    def normalizar_texto(cls, valor: str, info) -> str:
        valor = valor.strip()
        return valor.lower() if info.field_name == "email" else valor


def validar_senha(senha: str | None) -> str | None:
    if senha is not None and (not senha.strip() or len(senha.encode("utf-8")) > 72):
        raise ValueError("A senha deve conter de 6 a 72 bytes e não pode ser composta apenas por espaços")
    return senha


class UsuarioCreate(UsuarioBase):
    senha: str = Field(min_length=6, max_length=72)
    _validar_senha = field_validator("senha")(validar_senha)


class UsuarioUpdate(UsuarioBase):
    senha: str | None = Field(default=None, min_length=6, max_length=72)
    ativo: bool = True
    _validar_senha = field_validator("senha")(validar_senha)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
    ativo: bool
    perfil: str
    filiais: list[FilialOut]

    @field_validator("perfil", mode="before")
    @classmethod
    def nome_perfil(cls, valor):
        return getattr(valor, "nome", valor)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    perfil: str
    nome: str
    usuario_id: int
    filiais: list[FilialOut]


class ImpressoraUpdate(BaseModel):
    ip_impressora: str | None = None
    _validar_ip = field_validator("ip_impressora", mode="before")(FilialBase.validar_ip.__func__)


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
