from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Sistema de Gestão de Dietas Hospitalares"
    DATABASE_URL: str = "postgresql+asyncpg://dietas:dietas@localhost:5433/dietas"
    JWT_SECRET: str = "troque-este-segredo-em-producao"
    JWT_ALG: str = "HS256"
    JWT_EXPIRA_MINUTOS: int = 720
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
