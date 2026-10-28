"""Confere as medições salvas e consolida dados sem abrir o arquivo de credenciais."""
import argparse
import csv
import json
from pathlib import Path
import re
import statistics


def memoria_mib(valor):
    numero, unidade = re.fullmatch(r"([0-9.]+)\s*([a-zA-Z]+)", valor.strip()).groups()
    fatores = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3,
               "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    return float(numero) * fatores[unidade] / 1024**2


def consolidar(pasta):
    saida = {}
    for modo in ("lan", "wan"):
        resultado = json.loads((pasta / f"resultados-{modo}.json").read_text(encoding="utf-8"))
        recursos = json.loads((pasta / f"recursos-{modo}.json").read_text(encoding="utf-8"))
        with (pasta / f"requisicoes-{modo}.csv").open(encoding="utf-8", newline="") as arquivo:
            linhas = list(csv.DictReader(arquivo))
        for cenario in resultado["cenarios"]:
            if "solicitacoes" not in cenario:
                continue
            registros = [l for l in linhas if l["fase"] == cenario["nome"] and l["tipo"] == "solicitacao"]
            total = cenario["solicitacoes"]
            if not total or len(registros) != total or any(l["status"] not in ("200", "201") for l in registros):
                raise ValueError(f"Divergência de requisições: {cenario['nome']}")
            if any(v != total for v in cenario["integridade"].values()):
                raise ValueError(f"Divergência no banco: {cenario['nome']}")
            if cenario["websocket_todas_as_8_telas"] != total:
                raise ValueError(f"Falta de atualização de painel: {cenario['nome']}")
            impressao = cenario["impressao"]
            if impressao["pendentes"] or impressao["falhas"] or impressao["enviados"] != total:
                raise ValueError(f"Divergência na fila: {cenario['nome']}")
        if resultado["ws_fechados"] or resultado["unidade_incorreta"]:
            raise ValueError(f"Falha no WebSocket: {modo}")
        cpu = {s: [] for s in ("backend", "db", "frontend")}
        memoria = {s: [] for s in cpu}
        memoria_total, cpu_total = [], []
        for amostra in recursos:
            total_memoria, total_cpu = 0, 0
            for container in amostra["containers"]:
                servico = next(s for s in cpu if container["Name"].endswith(f"-{s}-1"))
                percentual = float(container["CPUPerc"].strip("%"))
                usada = memoria_mib(container["MemUsage"].split("/")[0])
                cpu[servico].append(percentual)
                memoria[servico].append(usada)
                total_memoria += usada
                total_cpu += percentual
            memoria_total.append(total_memoria)
            cpu_total.append(total_cpu)
        solicitacoes = [l for l in linhas if l["tipo"] == "solicitacao" and l["fase"] != "validacao_funcional"]
        paineis = [l for l in linhas if l["tipo"] == "painel"]
        presencas = [l for l in linhas if l["tipo"] == "presenca"]
        pings = [float(l["ms"]) for l in linhas if l["tipo"] == "websocket_ping"]
        protecao = [float(l["ms"]) for l in linhas if l["tipo"] == "protecao_aplicacao_atual"]
        saida[modo] = {
            "resultados": resultado,
            "amostras_recursos": len(recursos),
            "cpu_max_percentual_de_um_nucleo": {s: max(v) for s, v in cpu.items()},
            "cpu_media_percentual_de_um_nucleo": {s: statistics.mean(v) for s, v in cpu.items()},
            "cpu_max_total_nucleos": max(cpu_total) / 100,
            "cpu_max_percentual_dos_4_nucleos": max(cpu_total) / 4,
            "memoria_max_mib": {s: max(v) for s, v in memoria.items()},
            "memoria_total_max_mib": max(memoria_total),
            "solicitacoes_medidas": len(solicitacoes),
            "registros_totais": len(linhas),
            "paineis_http": len(paineis),
            "presencas_http": len(presencas),
            "erros_paineis": sum(l["status"] not in ("200", "304") for l in paineis),
            "erros_presencas": sum(l["status"] != "200" for l in presencas),
            "corpo_solicitacao_bytes_medio": statistics.mean(int(l["bytes_enviados"]) for l in solicitacoes),
            "resposta_solicitacao_bytes_medio": statistics.mean(int(l["bytes_recebidos"]) for l in solicitacoes),
            "ping_mediana_ms": statistics.median(pings) if pings else None,
            "ping_max_ms": max(pings) if pings else None,
            "aplicacao_real_probes": len(protecao),
            "aplicacao_real_max_ms": max(protecao) if protecao else None,
            "agendamento_max_ms": max(float(l["agendamento_ms"]) for l in solicitacoes),
        }
    reenvios = json.loads((pasta / "reenvios.json").read_text(encoding="utf-8"))
    if reenvios != {"requisicoes": 63, "retornos_201": 21, "retornos_200": 42, "pedidos": 21,
                    "chaves_distintas": 21, "trabalhos_impressao": 21, "resultado": "aprovado"}:
        raise ValueError("Divergência no teste de reenvios")
    saida["reenvios"] = reenvios
    return saida


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("laboratorio", type=Path)
    args = parser.parse_args()
    resumo = consolidar(args.laboratorio)
    destino = args.laboratorio / "resumo-completo.json"
    destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Medições conferidas: {sum(resumo[m]['solicitacoes_medidas'] for m in ('lan', 'wan'))} solicitações; {destino}")
