"""Cria backup e testa recuperação em banco descartável, sem iniciar a aplicação."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from app.core.config import BACKEND, settings
from app.services.recuperacao_backup import recuperar_e_conferir
from app.services.monitoramento import RelatorioBackup
from configurar_ambiente import gravar_privado


def publicar(caminho, teste, anterior):
    validado = teste if teste["estado"] == "VALIDADO" else anterior
    relatorio = {"versao": 1, "ultimo_teste": teste, "ultima_validacao": validado}
    RelatorioBackup.model_validate(relatorio)
    temporario = caminho.with_name(".resultado-" + uuid4().hex + ".json")
    gravar_privado(temporario, json.dumps(relatorio, ensure_ascii=False, indent=2))
    os.replace(temporario, caminho)


async def principal():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True, help="Contêiner PostgreSQL que contém o banco configurado")
    parser.add_argument("--pasta-backups", type=Path, default=BACKEND.parent / "backups")
    args = parser.parse_args()
    anterior = None
    caminho = settings.BACKUP_RELATORIO_ARQUIVO
    if caminho.exists():
        try:
            anterior = json.loads(caminho.read_text(encoding="utf-8")).get("ultima_validacao")
            RelatorioBackup.model_validate({"versao": 1, "ultimo_teste": anterior}) if anterior else None
        except (OSError, ValueError):
            raise SystemExit("Relatório anterior inválido. Confira o arquivo privado antes de executar.") from None
    print("Iniciando teste de recuperação em banco temporário; impressão e API da cópia não serão iniciadas.", flush=True)
    resultado = await recuperar_e_conferir(settings.DATABASE_URL, args.container, args.pasta_backups,
        progresso=lambda teste: publicar(caminho, teste, anterior))
    publicar(caminho, resultado, anterior)
    resumo = {k: resultado.get(k) for k in ("estado", "duracao_segundos", "tabelas_verificadas", "registros_verificados",
        "assinaturas_verificadas", "formularios_verificados", "sequencias_verificadas", "temporario_removido", "etapa", "erro_tipo")}
    print(json.dumps(resumo, ensure_ascii=True), flush=True)
    return 0 if resultado["estado"] == "VALIDADO" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
