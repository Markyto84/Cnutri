"""Ponto de entrada FastAPI — Sistema de Gestão de Dietas Hospitalares."""
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, assistencia, auth, cozinha, gestao, melhorias, monitoramento, operacao, pedidos, public_kiosk, relatorio_dietas, relatorios
from .core.config import settings
from .core.database import SessionLocal, engine
from .core.login_usuarios import migrar_login_usuarios
from .core.migracao_seguranca import migrar_seguranca
from .core.migracao_operacao import migrar_operacao
from .core.migracao_etiquetas import migrar_etiquetas
from .core.migracao_ad import migrar_ad
from .core.migracao_melhorias import migrar_melhorias
from .core.migracao_assistencia import migrar_assistencia
from .core.migracao_recebimento_qr import migrar_recebimento_qr
from .core.credenciais_iniciais import conferir_credenciais_producao
from .core.security import get_current_user, verificar_acesso_filial
from .core.ws import gerenciador_ws
from .models.models import Base
from .seed import executar_seed
from .services.fila_impressao import executar_fila
from .services.monitoramento import EstadoMonitoramento
from .services.contexto_operacao import executar_contexto
from .api import recebimento_qr

logging.basicConfig(level=logging.INFO)
INTERVALO_VALIDACAO_WS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria as tabelas (MVP; migrações com Alembic podem ser adicionadas depois)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(migrar_login_usuarios)
        await conn.run_sync(migrar_seguranca)
        await conn.run_sync(migrar_operacao)
        await conn.run_sync(migrar_etiquetas)
        await conn.run_sync(migrar_ad)
        await conn.run_sync(migrar_melhorias)
        await conn.run_sync(migrar_assistencia)
        await conn.run_sync(migrar_recebimento_qr)
    async with SessionLocal() as db:
        await executar_seed(db)
        if settings.APP_ENV == "production":
            await conferir_credenciais_producao(db)
    parar = asyncio.Event()
    app.state.monitoramento = EstadoMonitoramento()
    tarefa = asyncio.create_task(executar_fila(SessionLocal, parar, app.state.monitoramento.fila))
    contexto = asyncio.create_task(executar_contexto(SessionLocal, parar, gerenciador_ws))
    try:
        yield
    finally:
        parar.set()
        try:
            await asyncio.wait_for(asyncio.gather(tarefa, contexto), timeout=10)
        except TimeoutError:
            tarefa.cancel()
            contexto.cancel()
            await asyncio.gather(tarefa, contexto, return_exceptions=True)


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
app.include_router(relatorio_dietas.router)
app.include_router(operacao.router)
app.include_router(cozinha.router)
app.include_router(melhorias.router)
app.include_router(monitoramento.router)
app.include_router(assistencia.router)
app.include_router(recebimento_qr.router)


@app.middleware("http")
async def impedir_cache_clinico(request, call_next):
    resposta = await call_next(request)
    if request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/configuracao/instalacao")
async def configuracao_instalacao():
    # Somente o endereço distribuído aos clientes; configurações privadas não são expostas.
    return {"url_publica": settings.URL_PUBLICA or None}


@app.websocket("/ws/operacao/{filial_id}")
async def ws_operacao(websocket: WebSocket, filial_id: int):
    async with SessionLocal() as db:
        try:
            await operacao.unidade_ativa(filial_id, db)
        except HTTPException:
            await websocket.close(code=1008)
            return
    await gerenciador_ws.conectar_publico(filial_id, websocket)
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_json({"evento": "pong"})
    except Exception:
        pass
    finally:
        gerenciador_ws.desconectar(filial_id, websocket)


@app.websocket("/ws/cozinha/{filial_id}")
async def ws_cozinha(websocket: WebSocket, filial_id: int):
    """Painel Kanban da cozinha: recebe atualizações de pedidos em tempo real."""
    protocolos = websocket.scope.get("subprotocols", [])
    if len(protocolos) != 2 or protocolos[0] != "cnutri":
        await websocket.close(code=1008)
        return
    try:
        async with SessionLocal() as db:
            usuario = await get_current_user(protocolos[1], db)
            if usuario.troca_senha_obrigatoria:
                raise HTTPException(403, "Atualize sua senha antes de continuar")
            if usuario.perfil.nome not in (*pedidos.PERFIS_OPERACAO, "COPEIRA"):
                raise HTTPException(403, "Perfil sem acesso ao canal interno da cozinha")
            await verificar_acesso_filial(filial_id, usuario, db)
            usuario_id = usuario.id
    except HTTPException:
        await websocket.close(code=1008)
        return
    await gerenciador_ws.conectar(filial_id, websocket, usuario_id)
    proxima_validacao = asyncio.get_running_loop().time() + INTERVALO_VALIDACAO_WS
    try:
        while True:
            agora = asyncio.get_running_loop().time()
            if agora >= proxima_validacao:
                async with SessionLocal() as db:
                    atual = await get_current_user(protocolos[1], db)
                    await verificar_acesso_filial(filial_id, atual, db)
                    if atual.troca_senha_obrigatoria or atual.perfil.nome not in (*pedidos.PERFIS_OPERACAO, "COPEIRA"):
                        raise HTTPException(403, "Acesso encerrado")
                proxima_validacao = agora + INTERVALO_VALIDACAO_WS
            try:
                mensagem = await asyncio.wait_for(websocket.receive_text(), timeout=max(0.1, proxima_validacao - agora))
                if mensagem == "ping":
                    await websocket.send_json({"evento": "pong"})
            except TimeoutError:
                pass
    except HTTPException:
        await websocket.close(code=1008)
    except Exception:
        pass
    finally:
        gerenciador_ws.desconectar(filial_id, websocket)


@app.websocket("/ws/cozinha-publica/{filial_id}")
async def ws_cozinha_publica(websocket: WebSocket, filial_id: str):
    async with SessionLocal() as db:
        try:
            filial = await cozinha.resolver_unidade(filial_id, db)
            filial_id = filial.id
        except HTTPException:
            await websocket.close(code=1008)
            return
    await gerenciador_ws.conectar_cozinha(filial_id, websocket)
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_json({"evento": "pong"})
    except Exception:
        pass
    finally:
        gerenciador_ws.desconectar(filial_id, websocket)
