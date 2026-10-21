"""Schemas Pydantic de validação de entrada/saída."""
from datetime import datetime
from ipaddress import ip_address
from math import hypot
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.login_usuarios import PADRAO_USUARIO, normalizar_usuario

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
    nome_usuario: str = Field(min_length=3, max_length=50, pattern=PADRAO_USUARIO)
    perfil: Literal["ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA"]
    filial_ids: list[int] = Field(default_factory=list)

    @field_validator("nome", "nome_usuario", mode="before")
    @classmethod
    def normalizar_texto(cls, valor: str, info) -> str:
        if not isinstance(valor, str):
            return valor
        return normalizar_usuario(valor) if info.field_name == "nome_usuario" else valor.strip()


def validar_senha(senha: str | None) -> str | None:
    if senha is not None and (len(senha) < 12 or not senha.strip() or len(senha.encode("utf-8")) > 72):
        raise ValueError("A senha deve ter pelo menos 12 caracteres e no máximo 72 bytes")
    return senha


class UsuarioCreate(UsuarioBase):
    senha: str = Field(min_length=12, max_length=72)
    _validar_senha = field_validator("senha")(validar_senha)


class UsuarioUpdate(UsuarioBase):
    senha: str | None = Field(default=None, min_length=12, max_length=72)
    ativo: bool = True
    _validar_senha = field_validator("senha")(validar_senha)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    nome_usuario: str
    ativo: bool
    troca_senha_obrigatoria: bool
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
    troca_senha_obrigatoria: bool = False
    filiais: list[FilialOut]


class TrocaSenhaCreate(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=72)
    nova_senha: str = Field(min_length=12, max_length=72)
    _validar_senha = field_validator("nova_senha")(validar_senha)


class ImpressoraUpdate(BaseModel):
    ip_impressora: str | None = None
    _validar_ip = field_validator("ip_impressora", mode="before")(FilialBase.validar_ip.__func__)


class PresencaUpdate(BaseModel):
    filial_id: int = Field(gt=0)


class PontoAssinatura(BaseModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)


class AssinaturaCreate(BaseModel):
    tracos: list[Annotated[list[PontoAssinatura], Field(min_length=2, max_length=1500)]] = Field(min_length=1, max_length=40)

    @field_validator("tracos")
    @classmethod
    def validar_desenho(cls, tracos):
        if sum(len(traco) for traco in tracos) > 8000:
            raise ValueError("Assinatura muito extensa. Limpe o campo e assine novamente")
        comprimento = sum(hypot(b.x - a.x, b.y - a.y) for traco in tracos for a, b in zip(traco, traco[1:]))
        if comprimento < 0.08:
            raise ValueError("Desenhe a assinatura do recebedor no campo indicado")
        return tracos


class EntregaCreate(BaseModel):
    copeira_id: int = Field(gt=0)
    recebedor_nome: str = Field(min_length=3, max_length=120)
    assinatura: AssinaturaCreate

    @field_validator("recebedor_nome", mode="before")
    @classmethod
    def limpar_nome(cls, valor: str) -> str:
        return valor.strip() if isinstance(valor, str) else valor


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
    model_config = ConfigDict(extra="forbid")
    tipo_solicitacao: TipoSolicitacao
    solicitante_identificacao: str = Field(min_length=1, max_length=50, description="CRM, COREN ou Matrícula")
    solicitante_nome: str = Field(min_length=1, max_length=100)
    leito: str | None = Field(default=None, max_length=30)
    prontuario: str | None = Field(default=None, max_length=50)
    nome_paciente: str | None = Field(default=None, max_length=100)
    dieta_id: int | None = Field(default=None, gt=0, strict=True)
    observacoes_alergias: str | None = Field(default=None, max_length=5000)
    dados_dinamicos: dict[str, Any] = Field(default_factory=dict, max_length=100)

    @field_validator("solicitante_identificacao", "solicitante_nome", "leito", "prontuario", "nome_paciente", "observacoes_alergias", mode="before")
    @classmethod
    def limpar_textos(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class ImpressaoOut(BaseModel):
    id: int
    estado: str
    tentativas: int
    erro: str | None
    proxima_tentativa_em: datetime | None = None


class ReimpressaoCreate(BaseModel):
    confirmar_risco_duplicidade: bool = False


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
    impressao: ImpressaoOut | None = None


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
