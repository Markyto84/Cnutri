"""Endereço da instalação, sem dependências de banco ou da aplicação web."""
import ipaddress
import re
from urllib.parse import urlsplit


def normalizar_endereco_publico(valor: str, *, permitir_local: bool = True) -> str:
    mensagem = "Informe somente http:// ou https://, IP ou nome do servidor e porta opcional, sem caminhos ou credenciais."
    valor = valor.strip()
    if not valor or len(valor) > 300 or any(c.isspace() for c in valor) or any(c in valor for c in "\\?#"):
        raise ValueError(mensagem)
    try:
        partes = urlsplit(valor)
        host = (partes.hostname or "").lower().rstrip(".")
        porta = partes.port
    except ValueError:
        raise ValueError(mensagem) from None
    if partes.scheme not in ("http", "https") or not host or partes.username is not None or partes.password is not None or partes.path not in ("", "/") or porta is not None and not 1 <= porta <= 65535:
        raise ValueError(mensagem)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or re.fullmatch(r"[0-9.]+", host) or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in host.split(".")):
            raise ValueError(mensagem) from None
        if not permitir_local and (host == "localhost" or host.endswith(".localhost")):
            raise ValueError("Use o IP ou DNS que os outros computadores e celulares conseguem acessar.")
    else:
        if not permitir_local and (ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local):
            raise ValueError("Use o IP de rede do servidor, acessível aos outros computadores e celulares.")
        host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    sufixo = f":{porta}" if porta and porta != (443 if partes.scheme == "https" else 80) else ""
    return f"{partes.scheme}://{host}{sufixo}"
