from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "Sistema de Gestão de Dietas Hospitalares"
    APP_ENV: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = "postgresql+asyncpg://dietas:dietas@localhost:5433/dietas"
    JWT_SECRET: str = Field(min_length=32, repr=False)
    ADMIN_INICIAL_SENHA: str | None = Field(default=None, repr=False)
    JWT_ALG: str = "HS256"
    JWT_EXPIRA_MINUTOS: int = 720
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    AD_HABILITADO: bool = False
    AD_DOMINIO: str = ""
    AD_SERVIDOR: str = ""
    AD_BASE_DN: str = ""
    AD_CA_CERTIFICADO: str | None = None
    AD_TIMEOUT_SEGUNDOS: int = Field(default=5, ge=1, le=15)
    AD_SESSAO_MINUTOS: int = Field(default=30, ge=5, le=120)

    model_config = SettingsConfigDict(env_file=(BACKEND.parent / ".env", BACKEND / ".env"), env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def impedir_segredos_padrao(self):
        dns = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
        for nome in ("AD_DOMINIO", "AD_SERVIDOR"):
            valor = getattr(self, nome).strip().lower()
            if valor and not re.fullmatch(dns, valor):
                raise ValueError(f"{nome} deve conter um nome DNS completo, sem URL ou porta")
            setattr(self, nome, valor)
        if self.AD_HABILITADO and (not self.AD_DOMINIO or not self.AD_SERVIDOR):
            raise ValueError("Informe AD_DOMINIO e AD_SERVIDOR antes de habilitar o AD")
        if self.AD_HABILITADO and self.AD_CA_CERTIFICADO and not Path(self.AD_CA_CERTIFICADO).is_file():
            raise ValueError("Arquivo da autoridade certificadora do AD não encontrado")
        if self.JWT_SECRET.strip() == "troque-este-segredo-em-producao" or len(self.JWT_SECRET.strip()) < 32:
            raise ValueError("Configure JWT_SECRET com um segredo exclusivo de pelo menos 32 caracteres")
        if self.APP_ENV == "production":
            credencial_banco = make_url(self.DATABASE_URL).password or ""
            if credencial_banco == "dietas" or len(credencial_banco) < 12:
                raise ValueError("Configure a credencial exclusiva do banco de produção, com pelo menos 12 caracteres")
        return self


settings = Settings()
