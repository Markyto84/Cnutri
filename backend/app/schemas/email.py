import re
from ipaddress import ip_address
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, ValidationInfo, field_validator, model_validator

from ..services.endereco_email import normalizar_email


def normalizar_servidor(valor):
    try:
        return str(ip_address(valor))
    except ValueError:
        try:
            host = valor.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("Informe somente o nome ou IP do servidor SMTP, sem protocolo, caminho ou porta") from None
        if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in host.split(".")):
            raise ValueError("Informe somente o nome ou IP do servidor SMTP, sem protocolo, caminho ou porta")
        return host


class ConfiguracaoEmailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    modo: Literal["GOOGLE_APP", "GOOGLE_RELAY", "SMTP"] = "GOOGLE_APP"
    remetente: str = Field(max_length=254)
    servidor: str | None = Field(default=None, max_length=253)
    porta: int | None = Field(default=None, ge=1, le=65535, strict=True)
    seguranca: Literal["STARTTLS", "TLS", "SEM_TLS"] | None = None
    autenticar: bool | None = None
    usuario: str | None = Field(default=None, max_length=254)
    servidor_secundario: str | None = Field(default=None, max_length=253)
    porta_secundaria: int | None = Field(default=None, ge=1, le=65535, strict=True)
    tempo_limite: int = Field(default=30, ge=5, le=30, strict=True)
    endereco_resposta: str | None = Field(default=None, max_length=254)
    senha_app: SecretStr | None = Field(default=None, validation_alias=AliasChoices("senha", "senha_app"))
    habilitado: bool = False

    _validar_email = field_validator("remetente", mode="before")(normalizar_email)

    @field_validator("endereco_resposta", mode="before")
    @classmethod
    def conferir_resposta(cls, valor):
        return normalizar_email(valor) if valor is not None and valor != "" else None

    @field_validator("senha_app")
    @classmethod
    def validar_senha_app(cls, valor, info: ValidationInfo):
        if valor is None:
            return None
        senha = valor.get_secret_value()
        if info.data.get("modo") == "SMTP":
            if not senha or len(senha) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in senha):
                raise ValueError("Informe a credencial SMTP em uma linha, com até 512 caracteres")
            return valor
        senha = "".join(senha.split())
        if not re.fullmatch(r"[a-zA-Z0-9]{16}", senha):
            raise ValueError("Use a senha de app de 16 caracteres gerada pelo Google. A senha comum usada para abrir o e-mail não funciona nesta conexão. Gere a credencial no link exibido no painel")
        return SecretStr(senha)

    @field_validator("servidor", "servidor_secundario", "usuario", mode="before")
    @classmethod
    def limpar_conexao(cls, valor):
        if valor is None:
            return None
        if not isinstance(valor, str) or any(ord(c) < 32 or ord(c) == 127 for c in valor):
            raise ValueError("Informe um texto em uma linha")
        return valor.strip() or None

    @model_validator(mode="after")
    def validar_conexao(self):
        if self.servidor_secundario:
            self.servidor_secundario = normalizar_servidor(self.servidor_secundario)
            if self.porta_secundaria is None:
                raise ValueError("Informe a porta do servidor SMTP secundário")
        elif self.porta_secundaria is not None:
            raise ValueError("Informe o servidor SMTP secundário ou deixe sua porta vazia")
        if self.modo != "SMTP":
            self.servidor = "smtp.gmail.com" if self.modo == "GOOGLE_APP" else "smtp-relay.gmail.com"
            self.porta, self.seguranca = 587, "STARTTLS"
            self.autenticar = self.modo == "GOOGLE_APP"
            self.usuario = self.remetente if self.autenticar else None
            return self
        if not self.servidor or self.porta is None:
            raise ValueError("Informe o servidor SMTP e a porta fornecidos pela TI")
        self.servidor = normalizar_servidor(self.servidor)
        self.seguranca = self.seguranca or "STARTTLS"
        self.autenticar = True if self.autenticar is None else self.autenticar
        if self.autenticar and not self.usuario:
            raise ValueError("Informe o usuário usado para autenticar no servidor SMTP")
        if self.autenticar and self.seguranca == "SEM_TLS":
            raise ValueError("Para autenticar com usuário e senha, selecione STARTTLS ou SSL/TLS")
        if not self.autenticar:
            self.usuario = None
            if self.senha_app is not None:
                raise ValueError("Desative o envio de credencial quando a autenticação SMTP estiver desligada")
        return self


class ReenvioEmail(BaseModel):
    confirmar_risco_duplicidade: bool = False
