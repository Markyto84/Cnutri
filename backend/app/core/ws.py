"""Gerenciador de conexões WebSocket para o painel da cozinha (atualização em tempo real)."""
import asyncio
from collections import defaultdict

from fastapi import WebSocket
from ..services.operacao import pedido_operacional


class ConnectionManager:
    def __init__(self) -> None:
        # filial_id -> lista de websockets conectados (painéis da cozinha)
        self.ativos: dict[int, list[WebSocket]] = defaultdict(list)
        self.usuarios: dict[WebSocket, int] = {}
        self.publicos: dict[int, list[WebSocket]] = defaultdict(list)
        self.cozinhas: dict[int, list[WebSocket]] = defaultdict(list)

    async def conectar_cozinha(self, filial_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.cozinhas[filial_id].append(ws)

    async def conectar_publico(self, filial_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.publicos[filial_id].append(ws)

    async def conectar(self, filial_id: int, ws: WebSocket, usuario_id: int, subprotocolo: str = "cnutri") -> None:
        await ws.accept(subprotocol=subprotocolo)
        self.ativos[filial_id].append(ws)
        self.usuarios[ws] = usuario_id

    def desconectar(self, filial_id: int, ws: WebSocket) -> None:
        if ws in self.ativos[filial_id]:
            self.ativos[filial_id].remove(ws)
        self.usuarios.pop(ws, None)
        if ws in self.publicos[filial_id]:
            self.publicos[filial_id].remove(ws)
        if ws in self.cozinhas[filial_id]:
            self.cozinhas[filial_id].remove(ws)

    async def encerrar_unidade(self, filial_id: int) -> None:
        for ws in [*self.ativos.get(filial_id, []), *self.publicos.get(filial_id, []), *self.cozinhas.get(filial_id, [])]:
            self.desconectar(filial_id, ws)
            try:
                await ws.close(code=1008)
            except Exception:
                pass

    async def encerrar_usuario(self, usuario_id: int) -> None:
        for filial_id, conexoes in list(self.ativos.items()):
            for ws in list(conexoes):
                if self.usuarios.get(ws) == usuario_id:
                    self.desconectar(filial_id, ws)
                    try:
                        await ws.close(code=1008)
                    except Exception:
                        pass

    async def transmitir(self, filial_id: int, mensagem: dict) -> None:
        mortos: list[WebSocket] = []
        for ws in [*self.ativos[filial_id], *self.cozinhas[filial_id]]:
            try:
                interna = {"evento": mensagem.get("evento")}
                if mensagem.get("pedido"):
                    interna["pedido"] = pedido_operacional(mensagem["pedido"], autenticado=True)
                await ws.send_json(interna)
            except Exception:
                mortos.append(ws)
        for ws in mortos:
            self.desconectar(filial_id, ws)
        publica = {"evento": mensagem.get("evento")}
        if mensagem.get("pedido"):
            publica["pedido"] = pedido_operacional(mensagem["pedido"])
        for ws in list(self.publicos[filial_id]):
            try:
                await ws.send_json(publica)
            except Exception:
                self.desconectar(filial_id, ws)

    async def transmitir_contexto(self, filial_id: int, publico: dict, privado: dict) -> None:
        # Listas de copeiras nunca são transmitidas ao canal público.
        publica = {k: publico[k] for k in ("unidades", "alertas") if k in publico}
        interna = {**publica, **{k: privado[k] for k in ("copeiras",) if k in privado}}

        async def enviar(ws, dados):
            try:
                await asyncio.wait_for(ws.send_json({"evento": "contexto_atualizado", **dados}), timeout=5)
            except Exception:
                self.desconectar(filial_id, ws)
                try:
                    await ws.close(code=1011)
                except Exception:
                    pass

        envios = [enviar(ws, interna) for ws in list(self.ativos[filial_id])] if interna else []
        if publica:
            envios.extend(enviar(ws, publica) for ws in [*self.publicos[filial_id], *self.cozinhas[filial_id]])
        await asyncio.gather(*envios)


gerenciador_ws = ConnectionManager()
