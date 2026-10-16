"""Gerenciador de conexões WebSocket para o painel da cozinha (atualização em tempo real)."""
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # filial_id -> lista de websockets conectados (painéis da cozinha)
        self.ativos: dict[int, list[WebSocket]] = defaultdict(list)

    async def conectar(self, filial_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.ativos[filial_id].append(ws)

    def desconectar(self, filial_id: int, ws: WebSocket) -> None:
        if ws in self.ativos[filial_id]:
            self.ativos[filial_id].remove(ws)

    async def transmitir(self, filial_id: int, mensagem: dict) -> None:
        mortos: list[WebSocket] = []
        for ws in self.ativos[filial_id]:
            try:
                await ws.send_json(mensagem)
            except Exception:
                mortos.append(ws)
        for ws in mortos:
            self.desconectar(filial_id, ws)


gerenciador_ws = ConnectionManager()