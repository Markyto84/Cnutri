"""Schemas Pydantic de validação de entrada/saída."""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.login_usuarios import PADRAO_USUARIO, normalizar_usuario
from ..core.politica_senha import MIN_SENHA, MAX_SENHA, validar_senha
from ..core.codigos_unidades import validar_codigo_unidade
from ..modules.assinatura import AssinaturaCreate, PontoAssinatura  # compatibilidade com integrações existentes

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
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("ip_impressora", mode="before")
    @classmethod
    def validar_ip(cls, valor: str | None) -> str | None:
        if not valor or not valor.strip():
            return None
        try:
            return str(ip_address(valor.strip()))
        except ValueError:
            raise ValueError("Informe um endereço IP válido para a impressora")


class FilialEntrada(FilialBase):
    # A restrição vale na gravação. FilialOut ainda permite consultar cadastros antigos.
    _validar_codigo = field_validator("codigo_slug")(validar_codigo_unidade)


class FilialCreate(FilialEntrada):
    origem_filial_id: int | None = Field(default=None, gt=0)


class FilialUpdate(FilialEntrada):
    ativa: bool = True


class FilialOut(FilialBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ativa: bool


class ImpressoraEtiquetaUpdate(BaseModel):
    modelo: str = Field(default="", max_length=100)
    ip: str | None = None
    porta: int = Field(default=9100, ge=1, le=65535)
    protocolo: Literal["ZPL", "TSPL"] = "ZPL"
    resolucao: Literal[203, 300] = 203
    intervalo_mm: int = Field(default=2, ge=0, le=10)

    @field_validator("modelo")
    @classmethod
    def limpar_modelo(cls, valor):
        return valor.strip()

    @field_validator("ip")
    @classmethod
    def validar_ip_etiqueta(cls, valor):
        return FilialBase.validar_ip(valor)


class ImpressoraEtiquetaOut(ImpressoraEtiquetaUpdate):
    model_config = ConfigDict(from_attributes=True)
    filial_id: int


# ─── Usuários ────────────────────────────────────────────────────────────────
class UsuarioBase(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    nome_usuario: str = Field(min_length=3, max_length=50, pattern=PADRAO_USUARIO)
    perfil: Literal["ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA"]
    filial_ids: list[int] = Field(default_factory=list)
    origem_autenticacao: Literal["LOCAL", "AD"] = "LOCAL"
    usuario_ad: str | None = Field(default=None, max_length=254, pattern=r"^[^\s@\\\x00-\x1f\x7f]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")

    @field_validator("usuario_ad", mode="before")
    @classmethod
    def normalizar_ad(cls, valor):
        return valor.strip().lower() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def conferir_origem(self):
        if self.origem_autenticacao == "AD":
            if not self.usuario_ad:
                raise ValueError("Informe o usuário do AD no formato usuario@dominio")
            if getattr(self, "senha", None) is not None:
                raise ValueError("A senha do AD não deve ser cadastrada no Cnutri")
        elif self.usuario_ad is not None:
            raise ValueError("Vínculo AD disponível somente para contas do Active Directory")
        return self

    @field_validator("nome", "nome_usuario", mode="before")
    @classmethod
    def normalizar_texto(cls, valor: str, info) -> str:
        if not isinstance(valor, str):
            return valor
        return normalizar_usuario(valor) if info.field_name == "nome_usuario" else valor.strip()


class UsuarioCreate(UsuarioBase):
    senha: str | None = Field(default=None, min_length=MIN_SENHA, max_length=MAX_SENHA)
    _validar_senha = field_validator("senha")(validar_senha)

    @model_validator(mode="after")
    def exigir_senha_local(self):
        if self.origem_autenticacao == "LOCAL" and self.senha is None:
            raise ValueError("Informe uma senha temporária para a conta local")
        return self


class UsuarioUpdate(UsuarioBase):
    senha: str | None = Field(default=None, min_length=MIN_SENHA, max_length=MAX_SENHA)
    ativo: bool = True
    _validar_senha = field_validator("senha")(validar_senha)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    nome_usuario: str
    ativo: bool
    troca_senha_obrigatoria: bool
    origem_autenticacao: Literal["LOCAL", "AD"]
    usuario_ad: str | None
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
    origem_autenticacao: Literal["LOCAL", "AD"] = "LOCAL"
    filiais: list[FilialOut]


class TrocaSenhaCreate(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=72)
    nova_senha: str = Field(min_length=MIN_SENHA, max_length=MAX_SENHA)
    _validar_senha = field_validator("nova_senha")(validar_senha)


class ImpressoraUpdate(BaseModel):
    ip_impressora: str | None = None
    _validar_ip = field_validator("ip_impressora", mode="before")(FilialBase.validar_ip.__func__)


class PresencaUpdate(BaseModel):
    filial_id: int = Field(gt=0)


class AlertasUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preparo_minutos: int | None = Field(default=None, ge=1, le=1440, strict=True)
    entrega_minutos: int | None = Field(default=None, ge=1, le=1440, strict=True)


class EntregaCreate(BaseModel):
    copeira_id: int | None = Field(default=None, gt=0)
    # Compatibilidade com telas anteriores; a entrega atual dispensa comprovante.
    recebedor_nome: str | None = Field(default=None, min_length=3, max_length=120)
    assinatura: AssinaturaCreate | None = None

    @field_validator("recebedor_nome", mode="before")
    @classmethod
    def limpar_nome(cls, valor: str | None) -> str | None:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def conferir_comprovante(self):
        if (self.recebedor_nome is None) != (self.assinatura is None):
            raise ValueError("O comprovante deve conter o nome do recebedor e a assinatura, ou nenhum dos dois")
        return self


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
class ReferenciaPrescricao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    referencia: str = Field(min_length=1, max_length=150)
    data_hora: datetime
    prescritor_nome: str = Field(min_length=3, max_length=100)
    prescritor_registro: str = Field(min_length=3, max_length=100)

    @field_validator("referencia", "prescritor_nome", "prescritor_registro", mode="before")
    @classmethod
    def limpar_referencia(cls, valor):
        if isinstance(valor, str):
            valor = valor.strip()
            if any(ord(c) < 32 or ord(c) == 127 for c in valor):
                raise ValueError("Use um texto em uma linha")
        return valor

    @field_validator("data_hora")
    @classmethod
    def validar_horario(cls, valor):
        if valor.tzinfo is None:
            raise ValueError("Informe o fuso horário da prescrição")
        valor = valor.astimezone(timezone.utc)
        if valor > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("A prescrição não pode ter data e hora futuras")
        return valor


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
    prescricao: ReferenciaPrescricao | None = None

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
    etiqueta: ImpressaoOut | None = None
    prescricao: dict[str, Any] | None = None
    versao: int = 1
    recebimento_qr: bool = False


class PedidoAssistencialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1, strict=True)
    motivo: str = Field(min_length=5, max_length=1000)
    pedido: PedidoCreate
    confirmar_substituicao: bool = False

    @field_validator("motivo", mode="before")
    @classmethod
    def limpar_motivo(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class ConferenciaPrescricao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1, strict=True)


class StatusUpdate(BaseModel):
    status: StatusPedido
    motivo: str | None = Field(default=None, max_length=1000)

    @field_validator("motivo", mode="before")
    @classmethod
    def limpar_motivo(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def exigir_motivo_cancelamento(self):
        if self.status == "CANCELADO" and (not self.motivo or len(self.motivo) < 5):
            raise ValueError("Informe o motivo do cancelamento com pelo menos 5 caracteres")
        return self


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
