"""Carga funcional contra laboratório criado por ambiente.py; recusa destinos externos."""
import argparse
import asyncio
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import ssl
import subprocess
import time
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect

from ambiente import Laboratorio


def percentil(valores, p):
    if not valores:
        return None
    valores = sorted(valores)
    posicao = (len(valores) - 1) * p
    a, b = math.floor(posicao), math.ceil(posicao)
    return round(valores[a] + (valores[b] - valores[a]) * (posicao - a), 3)


class Carga:
    def __init__(self, lab, urls=None):
        self.lab = lab
        self.unidades = lab.unidades["unidades"]
        self.urls = urls or [lab.url] * len(self.unidades)
        self.sufixo = "wan" if urls else "lan"
        assert len(self.unidades) == 21 and all(u["slug"].startswith("simulacao-pico-") for u in self.unidades)
        assert all(url.startswith("https://127.0.0.1:") for url in self.urls)
        self.ssl = ssl.create_default_context(cafile=str(lab.cacert))
        self.clientes = [httpx.AsyncClient(base_url=url, verify=self.ssl, timeout=45,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=24)) for url in self.urls]
        self.registros = []
        self.recursos = []
        self.eventos = {}
        self.pedidos = []
        self.fase = "preparacao"
        self.tarefas = []
        self.sockets = []
        self.tags = {}
        self.pings = {}
        self.ws_bytes = 0
        self.ws_mensagens = 0
        self.ws_fechados = 0
        self.unidade_incorreta = 0
        self.interromper = asyncio.Event()
        self.fases = []

    async def requisitar(self, unidade, metodo, caminho, *, tipo, cabecalhos=None, corpo=None, planejado=None):
        fase = self.fase
        inicio = time.perf_counter()
        status, resposta, dados, saida, entrada = -1, None, None, 0, 0
        erro = None
        try:
            resposta = await self.clientes[unidade].request(metodo, caminho, headers=cabecalhos, json=corpo)
            status = resposta.status_code
            saida, entrada = len(resposta.request.content), len(resposta.content)
            if status not in (200, 201, 304):
                erro = resposta.text[:350]
            if status in (200, 201):
                dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            erro = type(exc).__name__
        duracao = (time.perf_counter() - inicio) * 1000
        registro = {"fase": fase, "tipo": tipo, "unidade": unidade + 1, "status": status,
            "ms": duracao, "agendamento_ms": max(0, (inicio - planejado) * 1000) if planejado else 0,
            "bytes_enviados": saida, "bytes_recebidos": entrada, "erro": erro}
        self.registros.append(registro)
        return dados, resposta, registro

    async def consultar_painel(self, unidade, painel):
        u = self.unidades[unidade]
        cabecalhos = {} if painel == 0 else {"Authorization": "Bearer " + u["tokens"][(painel - 1) % 5]}
        chave = (unidade, painel)
        if chave in self.tags:
            cabecalhos["If-None-Match"] = self.tags[chave]
        prefixo = "cozinha" if painel == 0 else "operacao"
        _, resposta, registro = await self.requisitar(unidade, "GET", f"/api/{prefixo}/unidades/{u['id']}/estado", tipo="painel", cabecalhos=cabecalhos)
        if resposta and resposta.headers.get("etag"):
            self.tags[chave] = resposta.headers["etag"]
        return registro

    async def observar(self, unidade, painel):
        u = self.unidades[unidade]
        url = self.urls[unidade].replace("https://", "wss://")
        caminho = f"/ws/cozinha-publica/{u['id']}" if painel == 0 else f"/ws/cozinha/{u['id']}"
        argumentos = {} if painel == 0 else {"subprotocols": ["cnutri", u["tokens"][(painel - 1) % 5]]}
        ws = await connect(url + caminho, ssl=self.ssl, ping_interval=None, open_timeout=45, max_size=8 * 1024 * 1024, **argumentos)
        self.sockets.append(ws)
        chave = (unidade, painel)
        async def receber():
            try:
                async for bruto in ws:
                    self.ws_bytes += len(bruto.encode() if isinstance(bruto, str) else bruto)
                    self.ws_mensagens += 1
                    msg = json.loads(bruto)
                    agora = time.perf_counter()
                    if msg.get("evento") == "pong" and chave in self.pings:
                        self.registros.append({"fase": self.fase, "tipo": "websocket_ping", "unidade": unidade + 1, "status": 200,
                            "ms": (agora - self.pings.pop(chave)) * 1000, "agendamento_ms": 0, "bytes_enviados": 4, "bytes_recebidos": len(bruto), "erro": None})
                    pedido = msg.get("pedido")
                    if pedido and "filial_id" in pedido and pedido["filial_id"] != u["id"]:
                        self.unidade_incorreta += 1
                    if msg.get("evento") == "novo_pedido" and pedido:
                        self.eventos.setdefault(pedido["id"], {})[chave] = agora
            except Exception:
                if not self.interromper.is_set():
                    self.ws_fechados += 1
        async def pulsar():
            while not self.interromper.is_set():
                await asyncio.sleep(25)
                self.pings[chave] = time.perf_counter()
                try:
                    await ws.send("ping")
                except Exception:
                    return
        self.tarefas.extend([asyncio.create_task(receber()), asyncio.create_task(pulsar())])

    async def abrir_paineis(self):
        self.fase = "abertura_168_paineis"
        inicio = time.perf_counter()
        consultas = await asyncio.gather(*[self.consultar_painel(u, p) for u in range(21) for p in range(8)])
        if any(r["status"] not in (200, 304) for r in consultas):
            raise RuntimeError("Falha ao abrir painéis no laboratório")
        await asyncio.gather(*[self.observar(u, p) for u in range(21) for p in range(8)])
        self.fases.append({"nome": self.fase, "duracao_s": time.perf_counter() - inicio,
            "conexoes": len(self.sockets), "p95_painel_ms": percentil([r["ms"] for r in consultas], .95)})

    async def rotina(self):
        async def presencas():
            while not self.interromper.is_set():
                await asyncio.gather(*[self.requisitar(u, "POST", "/api/auth/presenca", tipo="presenca",
                    cabecalhos={"Authorization": "Bearer " + token}, corpo={"filial_id": self.unidades[u]["id"]})
                    for u in range(21) for token in self.unidades[u]["tokens"]])
                await asyncio.sleep(30)
        async def reconciliar():
            while not self.interromper.is_set():
                await asyncio.sleep(120)
                await asyncio.gather(*[self.consultar_painel(u, p) for u in range(21) for p in range(8)])
        self.tarefas.extend([asyncio.create_task(presencas()), asyncio.create_task(reconciliar())])

    async def solicitar(self, unidade, contador, *, planejado=None, chave=None, corpo=None):
        u = self.unidades[unidade]
        chave = chave or str(uuid4())
        corpo = deepcopy(corpo or u["medico" if contador % 5 == 0 else "paciente"])
        if corpo["tipo_solicitacao"] == "PACIENTE":
            corpo["nome_paciente"] = f"PACIENTE FICTÍCIO TESTE {unidade+1:02}-{contador}"
            corpo["dados_dinamicos"]["matricula"] = f"TESTE-{contador}"
        inicio = time.perf_counter()
        dados, _, registro = await self.requisitar(unidade, "POST", f"/api/public/{u['slug']}/pedidos", tipo="solicitacao",
            cabecalhos={"Idempotency-Key": chave}, corpo=corpo, planejado=planejado)
        self.pedidos.append({"fase": registro["fase"], "chave": chave, "unidade": unidade, "id": dados.get("id") if dados else None,
            "inicio": inicio, "status": registro["status"], "ms": registro["ms"]})
        return dados, registro, corpo, chave

    async def executar_fase(self, nome, *, simultaneos=None, taxa=None, segundos=None):
        if self.interromper.is_set():
            raise RuntimeError("Carga interrompida pela proteção da aplicação em uso")
        self.fase = nome
        minimo = int(await asyncio.to_thread(self.lab.sql, "SELECT max(id) FROM pedidos;"))
        indice = len(self.pedidos)
        inicio = time.perf_counter()
        print(f"Iniciando {nome}: simultâneos={simultaneos}, taxa={taxa}, duração={segundos}", flush=True)
        if simultaneos:
            await asyncio.gather(*[self.solicitar(i % 21, i + 1) for i in range(simultaneos)])
        else:
            tarefas = []
            for i in range(round(taxa * segundos)):
                alvo = inicio + i / taxa
                await asyncio.sleep(max(0, alvo - time.perf_counter()))
                if self.interromper.is_set():
                    break
                tarefas.append(asyncio.create_task(self.solicitar(i % 21, i + 1, planejado=alvo)))
            await asyncio.gather(*tarefas)
        duracao = time.perf_counter() - inicio
        pedidos = self.pedidos[indice:]
        # Reconcilia no banco pelo comprovante aleatório, inclusive requisições incertas.
        chaves = ",".join("'" + p["chave"] + "'" for p in pedidos)
        integridade = json.loads(await asyncio.to_thread(self.lab.sql, f"SELECT json_build_object('registrados',count(*),'chaves_distintas',count(DISTINCT chave_envio),'ids_distintos',count(DISTINCT id)) FROM pedidos WHERE chave_envio IN ({chaves});"))
        fila = None
        limite = time.perf_counter() + 60
        self.fase = nome + "_drenagem"
        while True:
            fila = await asyncio.to_thread(self.lab.fila, minimo)
            if not fila["pendentes"] or time.perf_counter() >= limite:
                break
            await asyncio.sleep(2)
        resultado = {"nome": nome, "duracao_s": round(duracao, 3), "solicitacoes": len(pedidos), "sucessos_http": sum(p["status"] in (200, 201) for p in pedidos),
            "taxa_alvo_s": taxa, "taxa_concluida_s": round(len(pedidos) / duracao, 3), "p50_ms": percentil([p["ms"] for p in pedidos], .5),
            "p95_ms": percentil([p["ms"] for p in pedidos], .95), "p99_ms": percentil([p["ms"] for p in pedidos], .99), "max_ms": max(p["ms"] for p in pedidos),
            "integridade": integridade, "impressao": fila, "websocket_todas_as_8_telas": sum(len(self.eventos.get(p["id"], {})) == 8 for p in pedidos if p["id"]),
            "websocket_p95_ms": percentil([(max(self.eventos[p["id"]].values()) - p["inicio"]) * 1000 for p in pedidos if p["id"] in self.eventos and len(self.eventos[p["id"]]) == 8], .95)}
        self.fases.append(resultado)
        self.salvar()
        print(json.dumps(resultado, ensure_ascii=True), flush=True)
        total = len(pedidos)
        if self.interromper.is_set() or not total:
            raise RuntimeError("Cenário interrompido; os resultados parciais foram preservados")
        if resultado["sucessos_http"] != total or any(v != total for v in integridade.values()):
            raise RuntimeError("Falha ou divergência na gravação; consulte os resultados do cenário")
        if fila["pendentes"] or fila["falhas"] or fila["enviados"] != total:
            raise RuntimeError("A fila de impressão não concluiu o cenário; consulte os resultados")
        if resultado["websocket_todas_as_8_telas"] != total or self.unidade_incorreta or self.ws_fechados:
            raise RuntimeError("Falha na atualização das telas; consulte os resultados do cenário")
        await asyncio.to_thread(self.lab.isolar_fase, minimo)
        await asyncio.sleep(2)

    def salvar(self):
        dados = {"cenarios": self.fases, "ws_mensagens": self.ws_mensagens, "ws_bytes_aplicacao": self.ws_bytes,
            "ws_fechados": self.ws_fechados, "unidade_incorreta": self.unidade_incorreta}
        (self.lab.pasta / f"resultados-{self.sufixo}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.registros:
            with (self.lab.pasta / f"requisicoes-{self.sufixo}.csv").open("w", encoding="utf-8", newline="") as arquivo:
                writer = csv.DictWriter(arquivo, fieldnames=self.registros[0].keys())
                writer.writeheader()
                writer.writerows(self.registros)

    async def fechar(self):
        self.interromper.set()
        for t in self.tarefas:
            t.cancel()
        await asyncio.gather(*self.tarefas, return_exceptions=True)
        await asyncio.gather(*[s.close() for s in self.sockets], return_exceptions=True)
        await asyncio.gather(*[c.aclose() for c in self.clientes])
        self.salvar()


async def executar(lab, *, rede=False):
    urls = await asyncio.to_thread(lab.proxies) if rede else None
    carga = Carga(lab, urls)
    guard = httpx.AsyncClient(timeout=3)
    async def monitorar():
        while not carga.interromper.is_set():
            fase = carga.fase
            saida = await asyncio.to_thread(subprocess.check_output, ["docker", "stats", "--no-stream", "--format", "{{json .}}", *lab.ids.values()], text=True)
            carga.recursos.append({"fase": fase, "tempo": time.time(), "containers": [json.loads(l) for l in saida.splitlines()]})
            (lab.pasta / f"recursos-{carga.sufixo}.json").write_text(json.dumps(carga.recursos, indent=2), encoding="utf-8")
            await asyncio.sleep(4)
    async def proteger_atual():
        falhas = 0
        while not carga.interromper.is_set():
            inicio = time.perf_counter()
            try:
                r = await guard.get("http://127.0.0.1:5173/api/health/ready")
                ms = (time.perf_counter() - inicio) * 1000
                falhas = falhas + 1 if r.status_code != 200 or ms > 2500 else 0
                carga.registros.append({"fase": carga.fase, "tipo": "protecao_aplicacao_atual", "unidade": 0, "status": r.status_code, "ms": ms,
                    "agendamento_ms": 0, "bytes_enviados": 0, "bytes_recebidos": len(r.content), "erro": None})
            except httpx.HTTPError:
                falhas += 1
            if falhas >= 3:
                carga.interromper.set()
                print("Interrompendo carga: a aplicação em uso não respondeu no limite de proteção.", flush=True)
                return
            await asyncio.sleep(10)
    carga.tarefas.extend([asyncio.create_task(monitorar()), asyncio.create_task(proteger_atual())])
    try:
        async with httpx.AsyncClient(base_url=lab.url, verify=carga.ssl) as cliente:
            assert (await cliente.get("/api/configuracao/instalacao")).json()["url_publica"] == "https://carga.invalid"
        await asyncio.to_thread(lab.isolar_fase, lab.unidades["ultimo_id_inicial"])
        carga.fase = "validacao_funcional"
        for u in range(21):
            for contador in (1, 5):
                _, registro, _, _ = await carga.solicitar(u, contador)
                if registro["status"] != 201:
                    raise RuntimeError("Payload fictício inválido: " + str(registro["erro"]))
        minimo = lab.unidades["ultimo_id_inicial"]
        for _ in range(30):
            fila = await asyncio.to_thread(lab.fila, minimo)
            if fila["pendentes"] == 0:
                assert fila["falhas"] == 0, fila
                break
            await asyncio.sleep(2)
        await asyncio.to_thread(lab.isolar_fase, minimo)
        await carga.abrir_paineis()
        await carga.rotina()
        if rede:
            await carga.executar_fase("wan_100ms_5mbps_3.5_por_segundo", taxa=3.5, segundos=90)
            await carga.executar_fase("wan_100ms_5mbps_105_simultaneas", simultaneos=105)
        else:
            await carga.executar_fase("lan_21_simultaneas", simultaneos=21)
            await carga.executar_fase("lan_105_simultaneas", simultaneos=105)
            await carga.executar_fase("lan_210_simultaneas", simultaneos=210)
            await carga.executar_fase("lan_3.5_por_segundo", taxa=3.5, segundos=90)
            await carga.executar_fase("lan_20_por_segundo", taxa=20, segundos=60)
    finally:
        await carga.fechar()
        await guard.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("laboratorio", type=Path)
    parser.add_argument("--rede", action="store_true")
    args = parser.parse_args()
    laboratorio = Laboratorio.carregar(args.laboratorio)
    asyncio.run(executar(laboratorio, rede=args.rede))
