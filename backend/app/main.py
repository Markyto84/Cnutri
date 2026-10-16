"""Ponto de entrada FastAPI — Sistema de Gestão de Dietas Hospitalares."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, gestao, pedidos, public_kiosk, relatorios
from .core.config import settings
from .core.database import SessionLocal, engine
from .core.ws import gerenciador_ws
from .models.models import Base
from .seed import executar_seed

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria as tabelas (MVP; migrações com Alembic podem ser adicionadas depois)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await executar_seed(db)
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(public_kiosk.router)
app.include_router(pedidos.router)
app.include_router(gestao.router)
app.include_router(admin.router)
app.include_router(relatorios.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/cozinha/{filial_id}")
async def ws_cozinha(websocket: WebSocket, filial_id: int):
    """Painel Kanban da cozinha: recebe atualizações de pedidos em tempo real."""
    await gerenciador_ws.conectar(filial_id, websocket)
    try:
        while True:
            # Mantém a conexão viva; mensagens do cliente são ignoradas
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        gerenciador_ws.desconectar(filial_id, websocket)