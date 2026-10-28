"""Reenvios concorrentes no laboratório; verifica idempotência sem duplicar refeições."""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import ssl
from uuid import uuid4

import httpx
from ambiente import Laboratorio


async def principal(lab):
    contexto = ssl.create_default_context(cafile=str(lab.cacert))
    urls = [f"https://127.0.0.1:{lab.porta(f'rede{n:02}',8080)}" for n in range(1,22)]
    clientes = [httpx.AsyncClient(base_url=url, verify=contexto, timeout=30) for url in urls]
    chaves = [str(uuid4()) for _ in range(21)]
    try:
        assert (await clientes[0].get("/api/configuracao/instalacao")).json()["url_publica"] == "https://carga.invalid"
        chamadas = []
        for i, unidade in enumerate(lab.unidades["unidades"]):
            corpo = deepcopy(unidade["paciente"])
            for _ in range(3):
                chamadas.append(clientes[i].post(f"/api/public/{unidade['slug']}/pedidos", json=corpo, headers={"Idempotency-Key": chaves[i]}))
        respostas = await asyncio.gather(*chamadas)
        assert all(r.status_code in (200,201) for r in respostas)
        assert all(len({r.json()["id"] for r in respostas[i*3:i*3+3]}) == 1 for i in range(21))
        lista = ",".join("'"+c+"'" for c in chaves)
        contagens = json.loads(lab.sql(f"""SELECT json_build_object('pedidos',count(*),'chaves_distintas',count(DISTINCT chave_envio),
          'trabalhos_impressao',(SELECT count(*) FROM trabalhos_impressao WHERE pedido_id IN (SELECT id FROM pedidos WHERE chave_envio IN ({lista}))))
          FROM pedidos WHERE chave_envio IN ({lista});"""))
        assert contagens == {"pedidos":21,"chaves_distintas":21,"trabalhos_impressao":21}
        saida = {"requisicoes":63,"retornos_201":sum(r.status_code==201 for r in respostas),"retornos_200":sum(r.status_code==200 for r in respostas),**contagens,"resultado":"aprovado"}
        (lab.pasta / "reenvios.json").write_text(json.dumps(saida,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(saida),flush=True)
    finally:
        await asyncio.gather(*[c.aclose() for c in clientes])


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("laboratorio",type=Path)
    a=p.parse_args()
    asyncio.run(principal(Laboratorio.carregar(a.laboratorio)))
