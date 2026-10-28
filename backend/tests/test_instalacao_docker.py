"""Valida Linux e Nginx isolados; habilitar CNUTRI_TEST_DOCKER=1 e imagens oficiais locais."""
import http.client
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from test_https import certificado, chave

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_DOCKER") == "1", "Requer Docker de homologação")
class InstalacaoDockerTest(unittest.TestCase):
    def test_assistente_linux_preserva_segredos_e_permissoes(self):
        programa = '''import pathlib, subprocess, tempfile
with tempfile.TemporaryDirectory() as pasta:
    cmd = ['/bin/sh', '/codigo/servidor.sh', 'configurar', '--diretorio', pasta]
    primeira = subprocess.run(cmd + ['--endereco', 'http://192.0.2.10:8080'], check=True, capture_output=True, text=True)
    arquivo = pathlib.Path(pasta) / '.env'
    segredo = arquivo.read_bytes()
    assert arquivo.stat().st_mode & 0o777 == 0o600
    assert b'JWT_SECRET=' not in primeira.stdout.encode()
    subprocess.run(cmd + ['--endereco', 'https://ceres.test:8443', '--alterar'], check=True, capture_output=True)
    assert arquivo.read_bytes() == segredo
    assert 'URL_PUBLICA=https://ceres.test:8443' in (pathlib.Path(pasta) / 'work/servidor.env').read_text()
print('Assistente Linux: configuração, permissões privadas e segredos preservados.')
'''
        resultado = subprocess.run(["docker", "run", "--rm", "--network", "none", "--mount",
            f"type=bind,source={ROOT},target=/codigo,readonly", "python:3.12-slim", "python", "-B", "-c", programa],
            check=True, capture_output=True, text=True, timeout=45)
        self.assertIn("segredos preservados", resultado.stdout)

    def test_nginx_redireciona_para_porta_configurada_e_ignora_host_forjado(self):
        nome = "ceres-homologacao-" + uuid4().hex[:16]
        with TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            ca_key, servidor_key = chave(), chave()
            ca = certificado(ca_key)
            servidor = certificado(servidor_key, nomes=("ceres.test",), ca=ca, ca_key=ca_key)
            (pasta / "servidor.pem").write_bytes(servidor.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
            (pasta / "chave.pem").write_bytes(servidor_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            try:
                subprocess.run(["docker", "run", "--rm", "--detach", "--name", nome, "--publish", "127.0.0.1::80",
                    "--add-host", "backend:127.0.0.1", "--env", "CNUTRI_HOSTNAME=ceres.test", "--env", "CNUTRI_URL_PUBLICA=https://ceres.test:8443",
                    "--mount", f"type=bind,source={ROOT / 'infra/nginx-https.conf.template'},target=/etc/nginx/templates/default.conf.template,readonly",
                    "--mount", f"type=bind,source={pasta},target=/etc/nginx/cnutri-tls,readonly", "nginx:alpine"], check=True, capture_output=True, timeout=30)
                dados = json.loads(subprocess.check_output(["docker", "inspect", nome], text=True, timeout=10))[0]
                porta = int(dados["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"])
                for tentativa in range(30):
                    conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=2)
                    try:
                        conexao.request("GET", "/receber?teste=1", headers={"Host": "forjado.test"})
                        resposta = conexao.getresponse()
                        self.assertEqual(resposta.status, 308)
                        self.assertEqual(resposta.getheader("Location"), "https://ceres.test:8443/receber?teste=1")
                        break
                    except (OSError, http.client.HTTPException):
                        if tentativa == 29:
                            raise
                        time.sleep(0.1)
                    finally:
                        conexao.close()
            finally:
                subprocess.run(["docker", "stop", "--time", "2", nome], capture_output=True, timeout=15)
