from pathlib import Path
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

    model_config = SettingsConfigDict(env_file=(BACKEND.parent / ".env", BACKEND / ".env"), env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def impedir_segredos_padrao(self):
        if self.JWT_SECRET.strip() == "troque-este-segredo-em-producao" or len(self.JWT_SECRET.strip()) < 32:
            raise ValueError("Configure JWT_SECRET com um segredo exclusivo de pelo menos 32 caracteres")
        if self.APP_ENV == "production":
            credencial_banco = make_url(self.DATABASE_URL).password or ""
            if credencial_banco == "dietas" or len(credencial_banco) < 12:
                raise ValueError("Configure a credencial exclusiva do banco de produção, com pelo menos 12 caracteres")
        return self


settings = Settings()
