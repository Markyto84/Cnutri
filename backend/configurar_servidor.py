"""Assistente local de instalação. Prepara arquivos; não inicia serviços nem acessa o banco."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import string
import subprocess
import tempfile
from urllib.parse import urlsplit

from app.core.endereco_publico import normalizar_endereco_publico

ROOT = Path(__file__).resolve().parent.parent


def gravar_privado(caminho: Path, conteudo: str):
    if caminho.is_symlink():
        raise ValueError("A configuração deve ser um arquivo regular, sem link simbólico.")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(prefix=".configuracao-", dir=caminho.parent)
    temporario = Path(nome)
    try:
        if os.name == "nt":
            dono = subprocess.check_output(["whoami"], text=True).strip()
            subprocess.run(["icacls", nome, "/inheritance:r", "/grant:r", f"{dono}:(F)", "*S-1-5-18:(F)"], check=True, capture_output=True)
        with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
            descritor = None
            arquivo.write(conteudo)
        os.replace(temporario, caminho)
    finally:
        if descritor is not None:
            os.close(descritor)
        if temporario.exists():
            temporario.unlink()


def ler_configuracao(caminho):
    if caminho.is_symlink():
        raise ValueError("A configuração deve ser um arquivo regular, sem link simbólico.")
    if not caminho.exists():
        return {}
    return dict(linha.split("=", 1) for linha in caminho.read_text(encoding="utf-8").splitlines()
        if linha and not linha.startswith("#") and "=" in linha)


def senha_inicial():
    grupos = (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@%&*+-_")
    senha = [secrets.choice(grupo) for grupo in grupos]
    senha.extend(secrets.choice("".join(grupos)) for _ in range(12 - len(senha)))
    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)


def configurar(raiz, endereco, certificados=None, *, alterar=False):
    raiz = Path(raiz).resolve()
    if not raiz.is_dir() or raiz == Path(raiz.anchor):
        raise ValueError("Informe a pasta da instalação, já existente.")
    endereco = normalizar_endereco_publico(endereco, permitir_local=False)
    partes = urlsplit(endereco)
    https = partes.scheme == "https"
    pasta_tls = certificados or "/etc/ceres-care/tls"
    if not PurePosixPath(pasta_tls).is_absolute() or ".." in PurePosixPath(pasta_tls).parts or not re.fullmatch(r"/[a-zA-Z0-9_./-]+", pasta_tls):
        raise ValueError("Informe uma pasta Linux absoluta para os certificados, sem espaços ou parâmetros.")
    arquivo = raiz / "work/servidor.env"
    anterior = ler_configuracao(arquivo)
    porta_http = anterior.get("CNUTRI_PORTA_HTTP", "80") if https else str(partes.port or 80)
    if not porta_http.isdigit() or not 1 <= int(porta_http) <= 65535:
        raise ValueError("A porta HTTP anterior é inválida; confira a configuração existente.")
    porta_http = str(int(porta_http))
    porta_https = str(partes.port or 443) if https else "443"
    if https and porta_http == porta_https:
        raise ValueError("As portas HTTP e HTTPS precisam ser diferentes.")
    valores = {"URL_PUBLICA": endereco, "URL_RECEBIMENTO_PUBLICA": "${URL_PUBLICA}",
        "CNUTRI_HOSTNAME": partes.hostname, "CNUTRI_PORTA_HTTP": porta_http,
        "CNUTRI_PORTA_HTTPS": porta_https, "CNUTRI_HTTPS_ATIVO": "true" if https else "false",
        "CNUTRI_TLS_DIR": pasta_tls}
    conteudo = "# Configuração da instalação Ceres Care. Gerada pelo assistente local.\n"
    conteudo += "\n".join(f"{chave}={valor}" for chave, valor in valores.items()) + "\n"
    if anterior and anterior != valores and not alterar:
        raise ValueError("A instalação já possui um endereço. Use --alterar para preparar a mudança preservando as credenciais.")
    ambiente = raiz / ".env"
    credencial = raiz / "work/credencial-inicial.txt"
    if ambiente.is_symlink() or credencial.is_symlink():
        raise ValueError("Os arquivos privados devem ser regulares, sem links simbólicos.")
    if not ambiente.exists() and credencial.exists():
        raise ValueError("Há uma credencial inicial anterior sem o arquivo .env. Restaure a configuração privada da instalação.")
    if not ambiente.exists():
        senha = senha_inicial()
        gravar_privado(ambiente, f"POSTGRES_PASSWORD={secrets.token_hex(24)}\nJWT_SECRET={secrets.token_urlsafe(64)}\nADMIN_INICIAL_SENHA={json.dumps(senha)}\n")
        gravar_privado(credencial, f"Ceres Care — primeiro acesso de uma instalação nova\nUsuário: admin\nSenha temporária: {senha}\nA senha deve ser alterada no primeiro acesso. Este arquivo não redefine contas existentes.\n")
    if anterior != valores:
        if arquivo.exists():
            gravar_privado(raiz / "work/servidor.env.anterior", arquivo.read_text(encoding="utf-8"))
        gravar_privado(arquivo, conteudo)
    return {"url_publica": endereco, "https": https, "arquivo": str(arquivo), "credencial": str(credencial) if credencial.exists() else None}


def principal():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diretorio", type=Path, default=ROOT)
    parser.add_argument("--endereco", help="Endereço completo acessível aos computadores e celulares, por exemplo http://192.0.2.10:8080")
    parser.add_argument("--certificados", help="Pasta Linux com servidor.pem e chave.pem, para HTTPS")
    parser.add_argument("--alterar", action="store_true", help="Prepara outro endereço sem modificar senhas ou banco")
    args = parser.parse_args()
    try:
        endereco = args.endereco or input("Endereço da instalação (http://IP:porta ou https://domínio): ").strip()
        resultado = configurar(args.diretorio, endereco, args.certificados, alterar=args.alterar)
    except (ValueError, OSError, EOFError) as erro:
        parser.exit(1, f"Não foi possível preparar a configuração: {erro or 'informe --endereco no comando'}.\n")
    print("Configuração inicial preparada. Os serviços serão iniciados pelo comando iniciar.")
    print(f"Arquivo privado: {resultado['arquivo']}")
    for rotulo, caminho in (("Login", "/login"), ("Administração", "/admin"), ("Gestão", "/gestao"), ("Recebimento", "/receber")):
        print(f"{rotulo}: {resultado['url_publica']}{caminho}")
    print("Formulários e cozinhas usam os nomes das unidades cadastradas. Baixe os atalhos no painel de TI.")
    if resultado["credencial"]:
        print(f"Credencial inicial guardada somente no arquivo privado: {resultado['credencial']}")
    if resultado["https"]:
        print("Disponibilize o certificado e a chave na pasta informada e valide o DNS antes da ativação.")


if __name__ == "__main__":
    principal()
