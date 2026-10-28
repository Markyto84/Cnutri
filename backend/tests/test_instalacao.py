"""Instalação em pastas descartáveis; nenhum serviço ou banco real é alterado."""
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from dotenv import dotenv_values

from app.core.config import Settings, settings
from app.core.endereco_publico import normalizar_endereco_publico
from app.core.politica_senha import validar_senha
from app.main import app
from configurar_servidor import configurar, principal


class EnderecoInstalacaoTest(unittest.TestCase):
    def test_ip_dns_e_porta_produzem_origem_unica(self):
        for entrada, esperado in ((" HTTP://192.0.2.10:8080/ ", "http://192.0.2.10:8080"),
            ("https://Ceres.EXEMPLO.local:443/", "https://ceres.exemplo.local"),
            ("http://[2001:db8::10]:8080", "http://[2001:db8::10]:8080")):
            self.assertEqual(normalizar_endereco_publico(entrada), esperado)

    def test_rejeita_enderecos_que_nao_podem_ser_distribuidos(self):
        for valor in ("javascript:alert(1)", "http://pessoa:segredo@servidor.local", "https://servidor.local/admin",
            "https://servidor.local?token=1", "https://servidor.local#codigo", "http://servidor.local:0",
            "http://servidor.local:65536", "http://servidor.local\\login", "http://host\nforjado", "http://999.1.1.1",
            "http://localhost", "http://127.0.0.1", "http://0.0.0.0", "http://[::1]", "http://169.254.1.2"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                normalizar_endereco_publico(valor, permitir_local=False)

    def test_endereco_central_define_qr_e_cors_preservando_modo_anterior(self):
        argumentos = {"_env_file": None, "JWT_SECRET": "VALIDACAO-SEM-SEGREDO-" * 3, "APP_ENV": "test"}
        central = Settings(**argumentos, URL_PUBLICA="https://ceres.exemplo.local:8443/", URL_RECEBIMENTO_PUBLICA="http://192.0.2.10")
        self.assertEqual(central.URL_PUBLICA, "https://ceres.exemplo.local:8443")
        self.assertEqual(central.URL_RECEBIMENTO_PUBLICA, central.URL_PUBLICA)
        self.assertEqual(central.CORS_ORIGINS, [central.URL_PUBLICA])
        antigo = Settings(**argumentos, URL_RECEBIMENTO_PUBLICA="http://192.0.2.10/")
        self.assertIsNone(antigo.URL_PUBLICA)
        self.assertEqual(antigo.URL_RECEBIMENTO_PUBLICA, "http://192.0.2.10")


class AssistenteInstalacaoTest(unittest.TestCase):
    def test_primeira_instalacao_gera_privados_sem_exibir_senhas(self):
        with TemporaryDirectory() as pasta:
            root = Path(pasta)
            with patch.object(sys, "argv", ["configurar_servidor", "--diretorio", pasta, "--endereco", "http://192.0.2.10:8080"]):
                saida = StringIO()
                with redirect_stdout(saida):
                    principal()
            ambiente = dotenv_values(root / ".env")
            self.assertGreaterEqual(len(ambiente["POSTGRES_PASSWORD"]), 12)
            self.assertGreaterEqual(len(ambiente["JWT_SECRET"]), 32)
            validar_senha(ambiente["ADMIN_INICIAL_SENHA"])
            self.assertNotIn(ambiente["ADMIN_INICIAL_SENHA"], saida.getvalue())
            self.assertNotIn(ambiente["JWT_SECRET"], saida.getvalue())
            self.assertIn("http://192.0.2.10:8080/admin", saida.getvalue())
            self.assertIn(ambiente["ADMIN_INICIAL_SENHA"], (root / "work/credencial-inicial.txt").read_text(encoding="utf-8"))
            if os.name != "nt":
                self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)

    def test_troca_de_servidor_e_https_mantem_segredos_e_porta_anterior(self):
        with TemporaryDirectory() as pasta:
            root = Path(pasta)
            configurar(root, "http://192.0.2.10:8080")
            ambiente = (root / ".env").read_bytes()
            credencial = (root / "work/credencial-inicial.txt").read_bytes()
            anterior = (root / "work/servidor.env").read_bytes()
            configurar(root, "http://192.0.2.10:8080")
            with self.assertRaises(ValueError):
                configurar(root, "https://ceres.exemplo.local:8443")
            self.assertEqual((root / "work/servidor.env").read_bytes(), anterior)
            configurar(root, "https://ceres.exemplo.local:8443", alterar=True)
            parametros = dotenv_values(root / "work/servidor.env")
            self.assertEqual(parametros["URL_PUBLICA"], "https://ceres.exemplo.local:8443")
            self.assertEqual(parametros["URL_RECEBIMENTO_PUBLICA"], parametros["URL_PUBLICA"])
            self.assertEqual(parametros["CNUTRI_PORTA_HTTP"], "8080")
            self.assertEqual(parametros["CNUTRI_PORTA_HTTPS"], "8443")
            self.assertEqual(parametros["CNUTRI_HTTPS_ATIVO"], "true")
            self.assertEqual((root / ".env").read_bytes(), ambiente)
            self.assertEqual((root / "work/credencial-inicial.txt").read_bytes(), credencial)
            self.assertEqual((root / "work/servidor.env.anterior").read_bytes(), anterior)

    def test_entrada_invalida_nao_cria_ou_altera_arquivos(self):
        with TemporaryDirectory() as pasta:
            root = Path(pasta)
            for endereco, certificados in (("http://127.0.0.1", None), ("https://ceres.exemplo.local", "../../fora"),
                ("https://ceres.exemplo.local:80", None), ("http://192.0.2.10", "/etc/tls\nCNUTRI_HTTPS_ATIVO=true")):
                with self.assertRaises(ValueError):
                    configurar(root, endereco, certificados)
                self.assertEqual(list(root.iterdir()), [])

    def test_ambiente_privado_existente_permanece_intacto(self):
        with TemporaryDirectory() as pasta:
            root = Path(pasta)
            anterior = "POSTGRES_PASSWORD=senha-privada-ficticia\nJWT_SECRET=" + "segredo-ficticio" * 4 + "\n"
            (root / ".env").write_text(anterior, encoding="utf-8")
            configurar(root, "http://192.0.2.20")
            self.assertEqual((root / ".env").read_text(encoding="utf-8"), anterior)
            self.assertFalse((root / "work/credencial-inicial.txt").exists())


class ConfiguracaoPublicaTest(unittest.IsolatedAsyncioTestCase):
    async def test_consulta_so_expoe_endereco_sem_exigir_login_e_sem_cache(self):
        with patch.object(settings, "URL_PUBLICA", "https://ceres.exemplo.local"):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste") as cliente:
                resposta = await cliente.get("/api/configuracao/instalacao")
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.json(), {"url_publica": "https://ceres.exemplo.local"})
                self.assertIn("no-store", resposta.headers["Cache-Control"])
