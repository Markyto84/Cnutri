"""Prepara HTTPS com certificado da TI. Não acessa banco, AD ou impressoras."""
import argparse
from datetime import datetime, timezone
import getpass
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import sys
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID

from configurar_ambiente import gravar_privado

ROOT = Path(__file__).resolve().parent.parent


def normalizar_dominio(valor):
    valor = valor.strip().rstrip('.').lower()
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        pass
    if len(valor) > 253 or '.' not in valor or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in valor.split('.')):
        raise ValueError('Informe apenas o nome DNS completo da aplicação, sem protocolo, caminho ou porta.')
    return valor


def validar_certificado(dominio, certificado, chave):
    dominio = normalizar_dominio(dominio)
    agora = datetime.now(timezone.utc)
    if not certificado.not_valid_before_utc <= agora < certificado.not_valid_after_utc:
        raise ValueError('Certificado fora do período de validade.')
    formato = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if chave.public_key().public_bytes(*formato) != certificado.public_key().public_bytes(*formato):
        raise ValueError('A chave privada não corresponde ao certificado.')
    try:
        san = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        raise ValueError('Certificado sem SAN. Solicite à TI um certificado válido para o endereço da aplicação.') from None
    try:
        endereco = ipaddress.ip_address(dominio)
    except ValueError:
        nomes = [n.lower() for n in san.get_values_for_type(x509.DNSName)]
        corresponde = any(n == dominio or (n.startswith('*.') and n.count('*') == 1
            and len(n.split('.')) == len(dominio.split('.')) and dominio.endswith(n[1:])) for n in nomes)
    else:
        corresponde = endereco in san.get_values_for_type(x509.IPAddress)
    if not corresponde:
        raise ValueError('O certificado não cobre o endereço informado na extensão SAN.')
    try:
        if certificado.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError('Use um certificado de servidor, não um certificado de autoridade certificadora.')
    except x509.ExtensionNotFound:
        pass
    try:
        usos = certificado.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if ExtendedKeyUsageOID.SERVER_AUTH not in usos and ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE not in usos:
            raise ValueError('Certificado sem autorização para autenticação de servidor TLS.')
    except x509.ExtensionNotFound:
        pass
    return {'dominio': dominio, 'validade': certificado.not_valid_after_utc.isoformat(),
        'sha256': certificado.fingerprint(hashes.SHA256()).hex()}


def renderizar_caddy(dominio, certificado, chave, pasta_frontend, *, porta_https=443,
    portas_http=(80, 5173), upstream='127.0.0.1:8000', bind=None):
    dominio = normalizar_dominio(dominio)
    host = f'[{dominio}]' if ':' in dominio else dominio
    destino = f'https://{host}' + (f':{porta_https}' if porta_https != 443 else '')
    local = f'    bind {bind}\n' if bind else ''
    redirecionamentos = ''
    if portas_http:
        enderecos = ', '.join(f'http://:{p}' for p in portas_http)
        redirecionamentos = f'\n{enderecos} {{\n{local}    redir {destino}{{uri}} 308\n}}\n'
    return f'''{{
    admin off
    auto_https off
    persist_config off
    servers {{
        protocols h1 h2
    }}
}}

{destino} {{
{local}    tls {json.dumps(str(certificado))} {json.dumps(str(chave))}
    header X-Content-Type-Options nosniff
    header Referrer-Policy same-origin
    header Strict-Transport-Security "max-age=86400"
    request_body {{
        max_size 10MB
    }}
    @operacao path /api /api/* /ws /ws/*
    handle @operacao {{
        reverse_proxy {upstream} {{
            header_up X-Forwarded-Proto {{scheme}}
            header_up X-Forwarded-For {{remote_host}}
        }}
    }}
    handle /assets/* {{
        root * {json.dumps(str(pasta_frontend))}
        header Cache-Control "public, max-age=31536000, immutable"
        file_server
    }}
    handle {{
        root * {json.dumps(str(pasta_frontend))}
        header Cache-Control no-store
        try_files {{path}} /index.html
        file_server
    }}
}}
{redirecionamentos}'''


def preparar(dominio, *, certificado=None, chave=None, pfx=None, senha=None, raiz=ROOT):
    dominio = normalizar_dominio(dominio)
    for arquivo in (chave, pfx):
        if arquivo and Path(arquivo).resolve().is_relative_to((raiz / 'frontend').resolve()):
            raise ValueError('Mantenha chaves e PFX fora da pasta do frontend, para impedir publicação acidental.')
    try:
        if pfx:
            chave_obj, cert_obj, cadeia = pkcs12.load_key_and_certificates(Path(pfx).read_bytes(), senha)
            if chave_obj is None or cert_obj is None:
                raise ValueError('Pacote sem certificado e chave privada.')
            cadeia = [cert_obj, *(cadeia or [])]
        else:
            cadeia = x509.load_pem_x509_certificates(Path(certificado).read_bytes())
            cert_obj = cadeia[0]
            chave_obj = serialization.load_pem_private_key(Path(chave).read_bytes(), password=senha)
    except (ValueError, TypeError, IndexError, OSError):
        raise ValueError('Não foi possível abrir o certificado/chave. Confira o formato e, se aplicável, a senha local do arquivo.') from None
    dados = validar_certificado(dominio, cert_obj, chave_obj)
    pasta = raiz / 'work/https/generations' / uuid4().hex
    pasta.mkdir(parents=True)
    # O helper aplica ACL antes da escrita. PEM exportado nunca sai de work/.
    cert_path, key_path = pasta / 'servidor.pem', pasta / 'chave.pem'
    gravar_privado(cert_path, b''.join(c.public_bytes(serialization.Encoding.PEM) for c in cadeia).decode('ascii'))
    gravar_privado(key_path, chave_obj.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode('ascii'))
    dados.update(certificado=str(cert_path), chave=str(key_path), caddyfile=str(pasta / 'Caddyfile'),
        sonda=str(pasta / 'Caddyfile.sonda'), habilitado=True,
        url=f'https://[{dominio}]' if ':' in dominio else f'https://{dominio}')
    frontend = raiz / 'frontend/dist'
    gravar_privado(Path(dados['caddyfile']), renderizar_caddy(dominio, cert_path, key_path, frontend))
    gravar_privado(Path(dados['sonda']), renderizar_caddy(dominio, cert_path, key_path,
        frontend, porta_https=8443, portas_http=(), bind='127.0.0.1'))
    gravar_privado(pasta / 'config.json', json.dumps(dados, indent=2))
    return dados


def conferir_conexao(dominio, porta, contexto=None):
    contexto = contexto or ssl.create_default_context()
    with socket.create_connection(('127.0.0.1', porta), timeout=5) as bruto:
        with contexto.wrap_socket(bruto, server_hostname=dominio) as seguro:
            host = f'[{dominio}]' if ':' in dominio else dominio
            seguro.sendall(f'GET /api/health HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode('ascii'))
            resposta = http.client.HTTPResponse(seguro)
            resposta.begin()
            if resposta.status != 200 or json.loads(resposta.read()).get('status') != 'ok':
                raise ValueError('A API não respondeu corretamente pelo HTTPS.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dominio')
    parser.add_argument('--certificado')
    parser.add_argument('--chave')
    parser.add_argument('--pfx')
    parser.add_argument('--conferir-config')
    parser.add_argument('--testar-porta', type=int)
    args = parser.parse_args()
    try:
        if args.conferir_config:
            dados = json.loads(Path(args.conferir_config).read_text(encoding='utf-8-sig'))
            cert = x509.load_pem_x509_certificates(Path(dados['certificado']).read_bytes())[0]
            key = serialization.load_pem_private_key(Path(dados['chave']).read_bytes(), password=None)
            validar_certificado(dados['dominio'], cert, key)
            if args.testar_porta:
                conferir_conexao(dados['dominio'], args.testar_porta)
            print('Certificado, nome e chave conferidos.' + (' Conexão HTTPS confiável e API confirmadas.' if args.testar_porta else ''))
        else:
            if not args.dominio or not (args.pfx or (args.certificado and args.chave)):
                parser.error('Informe --dominio e --pfx, ou --certificado e --chave.')
            senha = None
            if args.pfx:
                if not sys.stdin.isatty():
                    raise ValueError('Abra o terminal local para informar a senha do PFX, sem enviá-la pelo chat.')
                senha = getpass.getpass('Senha do arquivo PFX (entrada oculta; Enter se não houver): ').encode() or None
            print(json.dumps(preparar(args.dominio, certificado=args.certificado, chave=args.chave, pfx=args.pfx, senha=senha)))
        return 0
    except (ValueError, OSError, ssl.SSLError):
        print('HTTPS não aplicado: confira domínio/SAN, validade, chave e confiança da CA. O acesso atual foi preservado.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
