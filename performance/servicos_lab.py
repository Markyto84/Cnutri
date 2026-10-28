"""Serviços descartáveis da simulação: coletor TCP de impressão e proxy de rede."""
import asyncio
import json
import os
import time

CONTADORES = {"conexoes": 0, "bytes": 0, "concluidas": 0}
INICIO = time.monotonic()


async def impressora(reader, writer):
    CONTADORES["conexoes"] += 1
    try:
        while dados := await reader.read(65536):
            CONTADORES["bytes"] += len(dados)
        CONTADORES["concluidas"] += 1
    finally:
        writer.close()
        await writer.wait_closed()


async def estatisticas(reader, writer):
    await reader.readuntil(b"\r\n\r\n")
    corpo = json.dumps({**CONTADORES, "segundos": time.monotonic() - INICIO}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(corpo)).encode() + b"\r\n\r\n" + corpo)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def proxy(reader, writer):
    remoto = None
    try:
        entrada, remoto = await asyncio.open_connection(os.environ.get("DESTINO", "frontend"), int(os.environ.get("PORTA_DESTINO", "443")))
        async def transferir(origem, destino):
            while dados := await origem.read(65536):
                destino.write(dados)
                await destino.drain()
        tarefas = [asyncio.create_task(transferir(reader, remoto)), asyncio.create_task(transferir(entrada, writer))]
        _, pendentes = await asyncio.wait(tarefas, return_when=asyncio.FIRST_COMPLETED)
        for tarefa in pendentes:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()
        if remoto:
            remoto.close()


async def principal():
    if os.environ.get("MODO") == "proxy":
        servidor = await asyncio.start_server(proxy, "0.0.0.0", 8080)
        async with servidor:
            await servidor.serve_forever()
    else:
        tcp = await asyncio.start_server(impressora, "0.0.0.0", 9100)
        http = await asyncio.start_server(estatisticas, "0.0.0.0", 9000)
        async with tcp, http:
            await asyncio.gather(tcp.serve_forever(), http.serve_forever())


if __name__ == "__main__":
    asyncio.run(principal())
