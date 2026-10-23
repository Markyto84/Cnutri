"""Valida uma conta previamente autorizada no Cnutri via LDAPS, sem guardar a senha.

Usa o próprio usuário no bind e na consulta da identidade; não exige uma conta de
serviço nem altera o diretório. A chamada síncrona deve executar fora do event loop.
"""
from contextlib import suppress
import ssl
from uuid import UUID

from ldap3 import Connection, NONE, Server, SIMPLE, SUBTREE, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from ..core.config import settings


class ADIndisponivel(Exception):
    """Erro de configuração, conexão ou consulta; nunca inclui respostas do AD."""


def situacao_ad():
    return {
        "habilitado": settings.AD_HABILITADO,
        "configurado": bool(settings.AD_SERVIDOR and settings.AD_DOMINIO),
        "dominio": settings.AD_DOMINIO,
        "servidor": settings.AD_SERVIDOR,
        "sessao_minutos": settings.AD_SESSAO_MINUTOS,
    }


def autenticar_ad(principal: str, senha: str) -> str | None:
    if not settings.AD_HABILITADO or not settings.AD_SERVIDOR or not settings.AD_DOMINIO:
        raise ADIndisponivel()
    # Senha vazia pode ser interpretada como bind anônimo por servidores LDAP.
    if not principal or not senha or "\x00" in senha or len(senha.encode("utf-8")) > 1024:
        return None
    conexao = None
    try:
        tls = Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT,
            ca_certs_file=settings.AD_CA_CERTIFICADO, valid_names=[settings.AD_SERVIDOR], sni=settings.AD_SERVIDOR)
        servidor = Server(settings.AD_SERVIDOR, port=636, use_ssl=True, tls=tls,
            get_info=NONE, connect_timeout=settings.AD_TIMEOUT_SEGUNDOS)
        conexao = Connection(servidor, user=principal, password=senha, authentication=SIMPLE,
            auto_referrals=False, receive_timeout=settings.AD_TIMEOUT_SEGUNDOS,
            raise_exceptions=False)
        if not conexao.bind():
            if conexao.result and conexao.result.get("result") == 49:
                return None  # senha inválida, expirada, bloqueio ou conta desativada.
            raise ADIndisponivel()
        base = settings.AD_BASE_DN or ",".join(f"DC={parte}" for parte in settings.AD_DOMINIO.split("."))
        filtro = f"(&(objectCategory=person)(objectClass=user)(userPrincipalName={escape_filter_chars(principal)}))"
        conexao.search(base, filtro, search_scope=SUBTREE, size_limit=2,
            time_limit=settings.AD_TIMEOUT_SEGUNDOS, attributes=["objectGUID", "userAccountControl", "userPrincipalName"])
        if not conexao.result or conexao.result.get("result") != 0:
            raise ADIndisponivel()
        entradas = [e for e in conexao.response if e.get("type") == "searchResEntry"]
        if len(entradas) != 1:
            return None
        atributos = entradas[0].get("raw_attributes", {})
        guids, flags = atributos.get("objectGUID", []), atributos.get("userAccountControl", [])
        upns = atributos.get("userPrincipalName", [])
        if len(guids) != 1 or len(flags) != 1 or len(upns) != 1:
            return None
        if upns[0].decode("utf-8").lower() != principal.lower() or int(flags[0]) & 2:
            return None
        return str(UUID(bytes_le=guids[0]))
    except (LDAPException, OSError, ValueError, UnicodeError):
        raise ADIndisponivel() from None
    finally:
        if conexao:
            with suppress(LDAPException, OSError):
                conexao.unbind()
