"""Provisiona segredos locais sem imprimir seus valores nem versioná-los."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

from dotenv import dotenv_values
from app.core.politica_senha import gerar_senha_temporaria

BACKEND = Path(__file__).resolve().parent


def gravar_privado(caminho: Path, conteudo: str):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not caminho.exists():
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descritor)
    if os.name == "nt":
        dono = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(caminho), "/inheritance:r", "/grant:r", f"{dono}:(F)", "*S-1-5-18:(F)"], check=True, capture_output=True)
    else:
        caminho.chmod(0o600)
    caminho.write_text(conteudo, encoding="utf-8")


def configurar():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicializar-admin", action="store_true")
    args = parser.parse_args()
    caminho = BACKEND / ".env"
    valores = dotenv_values(caminho) if caminho.exists() else {}
    linhas = caminho.read_text(encoding="utf-8") if caminho.exists() else ""
    atual = valores.get("JWT_SECRET", "") or ""
    if len(atual.encode()) < 32 or atual == "troque-este-segredo-em-producao":
        linhas += "\nJWT_SECRET=" + json.dumps(secrets.token_urlsafe(64)) + "\n"
    if args.inicializar_admin and not valores.get("ADMIN_INICIAL_SENHA"):
        linhas += "ADMIN_INICIAL_SENHA=" + json.dumps(gerar_senha_temporaria()) + "\n"
    gravar_privado(caminho, linhas)
    print(f"Configuração privada preparada em {caminho}. Nenhum segredo foi exibido.")


if __name__ == "__main__":
    configurar()
