"""Certificados de teste descartáveis; não instala CA nem acessa dados do hospital."""
import asyncio
from datetime import datetime, timedelta, timezone
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import uvicorn
from websockets.asyncio.client import connect

from https_config import normalizar_dominio, preparar, renderizar_caddy, validar_certificado


def chave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def certificado(key, *, nomes=('cnutri.test',), inicio=-1, fim=24, ca=None, ca_key=None, uso=ExtendedKeyUsageOID.SERVER_AUTH, incluir_san=True):
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Autoridade fictícia Cnutri' if ca is None else 'Servidor fictício Cnutri')])
    agora = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(nome).issuer_name(ca.subject if ca else nome)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(agora + timedelta(hours=inicio)).not_valid_after(agora + timedelta(hours=fim))
        .add_extension(x509.BasicConstraints(ca=ca is None, path_length=None), critical=True))
    if incluir_san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in nomes]), critical=False)
    if ca:
        builder = builder.add_extension(x509.ExtendedKeyUsage([uso]), critical=False)
    return builder.sign(ca_key or key, hashes.SHA256())


class CertificadoHttpsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ca_key = chave()
        cls.ca = certificado(cls.ca_key)
        cls.key = chave()
        cls.cert = certificado(cls.key, ca=cls.ca, ca_key=cls.ca_key)

    def test_confere_dominio_san_validade_e_chave_sem_emitir_certificado(self):
        self.assertEqual(validar_certificado('CNUTRI.TEST', self.cert, self.key)['dominio'], 'cnutri.test')
        with self.assertRaises(ValueError):
            validar_certificado('outra.test', self.cert, self.key)
        with self.assertRaises(ValueError):
            validar_certificado('cnutri.test', self.cert, chave())

    def test_recusa_ca_certificado_expirado_futuro_sem_san_ou_so_cliente(self):
        for cert in (self.ca,
            certificado(self.key, ca=self.ca, ca_key=self.ca_key, inicio=-24, fim=-1),
            certificado(self.key, ca=self.ca, ca_key=self.ca_key, inicio=1, fim=24),
            certificado(self.key, ca=self.ca, ca_key=self.ca_key, incluir_san=False),
            certificado(self.key, ca=self.ca, ca_key=self.ca_key, uso=ExtendedKeyUsageOID.CLIENT_AUTH)):
            with self.assertRaises(ValueError):
                validar_certificado('cnutri.test', cert, self.ca_key if cert is self.ca else self.key)

    def test_wildcard_cobre_apenas_um_nivel(self):
        cert = certificado(self.key, nomes=('*.empresa.local',), ca=self.ca, ca_key=self.ca_key)
        validar_certificado('cnutri.empresa.local', cert, self.key)
        for host in ('empresa.local', 'outro.cnutri.empresa.local', 'cnutri.outra.local'):
            with self.assertRaises(ValueError):
                validar_certificado(host, cert, self.key)

    def test_rejeita_url_porta_caminho_e_injecao_no_dominio(self):
        for valor in ('https://cnutri.test', 'cnutri.test:443', 'cnutri.test/abc', 'cnutri.test\nlocalhost', 'cnutri.test{admin}', '-abc.test'):
            with self.assertRaises(ValueError):
                normalizar_dominio(valor)

    def test_pfx_com_senha_prepara_geracao_privada_sem_ativar(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            pfx = root / 'entrada.pfx'
            pfx.write_bytes(pkcs12.serialize_key_and_certificates(b'teste', self.key, self.cert,
                [self.ca], serialization.BestAvailableEncryption(b'SenhaSomenteTeste')))
            cfg = preparar('cnutri.test', pfx=pfx, senha=b'SenhaSomenteTeste', raiz=root)
            self.assertFalse((root / 'work/https/active.json').exists())
            self.assertIn('work', Path(cfg['chave']).parts)
            self.assertNotIn('SenhaSomenteTeste', Path(cfg['caddyfile']).read_text())
            self.assertEqual(len(x509.load_pem_x509_certificates(Path(cfg['certificado']).read_bytes())), 2)
            with self.assertRaises(ValueError):
                preparar('cnutri.test', pfx=pfx, senha=b'errada', raiz=root)
            publico = root / 'frontend/public'
            publico.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'fora da pasta do frontend'):
                preparar('cnutri.test', pfx=publico / 'entrada.pfx', senha=b'SenhaSomenteTeste', raiz=root)

    def test_configuracao_mantem_caminhos_e_cabecalhos_seguros(self):
        texto = renderizar_caddy('cnutri.test', r'C:\Pasta com espaço\servidor.pem', r'C:\Pasta com espaço\chave.pem', r'C:\app\dist')
        self.assertIn('auto_https off', texto)
        self.assertIn('admin off', texto)
        self.assertIn('http://:80, http://:5173', texto)
        self.assertIn('redir https://cnutri.test{uri} 308', texto)
        self.assertNotIn('redir https://{host}', texto)
        self.assertIn('header_up X-Forwarded-Proto {scheme}', texto)
        self.assertIn('/ws/*', texto)


def porta_livre():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


async def app_ficticio(scope, receive, send):
    if scope['type'] == 'http':
        headers = dict(scope['headers'])
        dados = json.dumps({'status': 'ok', 'request_scheme': scope['scheme'], 'scheme': headers.get(b'x-forwarded-proto', b'').decode(),
            'client': headers.get(b'x-forwarded-for', b'').decode(), 'path': scope['path']}).encode()
        await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
        await send({'type': 'http.response.body', 'body': dados})
    elif scope['type'] == 'websocket':
        await receive()
        await send({'type': 'websocket.accept'})
        mensagem = await receive()
        await send({'type': 'websocket.send', 'text': mensagem.get('text', '')})
        await send({'type': 'websocket.close', 'code': 1000})


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_CADDY'), 'Requer Caddy de teste explicitamente indicado')
class GatewayHttpsTest(unittest.TestCase):
    def test_https_redirect_spa_api_certificados_e_websocket(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ca_key, key = chave(), chave()
            ca = certificado(ca_key)
            cert = certificado(key, ca=ca, ca_key=ca_key)
            cert_path, key_path = root / 'server.pem', root / 'key.pem'
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            frontend = root / 'frontend'
            frontend.mkdir()
            (frontend / 'index.html').write_text('<html>Cnutri fictício HTTPS</html>', encoding='utf-8')
            porta_api, porta_tls, porta_http, porta_antiga = (porta_livre() for _ in range(4))
            api = uvicorn.Server(uvicorn.Config(app_ficticio, host='127.0.0.1', port=porta_api, lifespan='off', log_level='error'))
            thread = threading.Thread(target=api.run, daemon=True)
            thread.start()
            cfg = root / 'Caddyfile'
            cfg.write_text(renderizar_caddy('cnutri.test', cert_path, key_path, frontend,
                porta_https=porta_tls, portas_http=(porta_http, porta_antiga), upstream=f'127.0.0.1:{porta_api}', bind='127.0.0.1'), encoding='utf-8')
            contexto = ssl.create_default_context(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())

            def requisitar(caminho, contexto_tls=contexto, host_tls='cnutri.test'):
                with socket.create_connection(('127.0.0.1', porta_tls), timeout=3) as raw:
                    with contexto_tls.wrap_socket(raw, server_hostname=host_tls) as sock:
                        sock.sendall((f'GET {caminho} HTTP/1.1\r\nHost: cnutri.test:{porta_tls}\r\nX-Forwarded-Proto: http\r\nX-Forwarded-For: 8.8.8.8\r\nConnection: close\r\n\r\n').encode())
                        resposta = http.client.HTTPResponse(sock)
                        resposta.begin()
                        return resposta.status, resposta.read(), dict(resposta.getheaders())

            with (root / 'caddy.log').open('w', encoding='utf-8') as log:
                processo = subprocess.Popen([os.environ['CNUTRI_TEST_CADDY'], 'run', '--config', str(cfg), '--adapter', 'caddyfile'], stdout=log, stderr=log)
                try:
                    prazo = time.monotonic() + 10
                    ultimo = None
                    while True:
                        if processo.poll() is not None:
                            self.fail((root / 'caddy.log').read_text(encoding='utf-8'))
                        try:
                            status, dados, _ = requisitar('/api/health')
                            ultimo = f'HTTP {status}: {dados!r}'
                            if status == 200:
                                break
                        except OSError as erro:
                            ultimo = str(erro)
                        if time.monotonic() > prazo:
                            self.fail(f'Gateway fictício não iniciou: {ultimo}\n' + (root / 'caddy.log').read_text(encoding='utf-8'))
                        time.sleep(.1)
                    dados = json.loads(dados)
                    self.assertEqual(dados['scheme'], 'https')
                    self.assertEqual(dados['request_scheme'], 'https')
                    self.assertEqual(dados['client'], '127.0.0.1')
                    status, html, headers = requisitar('/gestao')
                    self.assertEqual(status, 200)
                    self.assertIn(b'HTTPS', html)
                    self.assertIn('max-age=86400', headers['Strict-Transport-Security'])
                    for porta in (porta_http, porta_antiga):
                        conexao = http.client.HTTPConnection('127.0.0.1', porta, timeout=3)
                        conexao.request('GET', '/entregas/1?teste=1', headers={'Host': 'host-forjado.test'})
                        resposta = conexao.getresponse()
                        self.assertEqual(resposta.status, 308)
                        self.assertEqual(resposta.getheader('Location'), f'https://cnutri.test:{porta_tls}/entregas/1?teste=1')
                        conexao.close()
                    for ctx, host in ((ssl.create_default_context(), 'cnutri.test'), (contexto, 'outro.test')):
                        with self.assertRaises(ssl.SSLError):
                            requisitar('/api/health', ctx, host)

                    async def websocket():
                        async with connect(f'wss://cnutri.test:{porta_tls}/ws/operacao/1', host='127.0.0.1', port=porta_tls, ssl=contexto, proxy=None) as ws:
                            await ws.send('mensagem fictícia')
                            self.assertEqual(await ws.recv(), 'mensagem fictícia')
                    asyncio.run(websocket())
                finally:
                    processo.terminate()
                    processo.wait(timeout=5)
                    api.should_exit = True
                    thread.join(timeout=5)
