import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..services.endereco_email import normalizar_email


class ConfiguracaoEmailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    modo: Literal["GOOGLE_APP", "GOOGLE_RELAY"] = "GOOGLE_APP"
    remetente: str = Field(max_length=254)
    senha_app: SecretStr | None = None
    habilitado: bool = False

    _validar_email = field_validator("remetente", mode="before")(normalizar_email)

    @field_validator("senha_app")
    @classmethod
    def validar_senha_app(cls, valor):
        if valor is None:
            return None
        senha = valor.get_secret_value().replace(" ", "")
        if not re.fullmatch(r"[a-zA-Z0-9]{16}", senha):
            raise ValueError("Use a senha de app de 16 caracteres gerada pelo Google")
        return SecretStr(senha)


class ReenvioEmail(BaseModel):
    confirmar_risco_duplicidade: bool = False
