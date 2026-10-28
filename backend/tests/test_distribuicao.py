"""Empacotamento com carga fictícia e extração Linux em diretórios descartáveis."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from gerar_instalador import ROOT, preparar_conteudo, gerar_run, versao_valida


class DistribuicaoTest(unittest.TestCase):
    def test_conteudo_explicito_preserva_configuracao_sem_levar_privados(self):
        with TemporaryDirectory() as pasta:
            destino = Path(pasta)
            preparar_conteudo(ROOT, destino, "0.1.0-teste")
            arquivos = [p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file()]
            self.assertNotIn(".env", arquivos)
            self.assertNotIn("backend/.env", arquivos)
            self.assertFalse(any("backups/" in p or "work/" in p or "node_modules/" in p for p in arquivos))
            compose = (destino / "docker-compose.prod.yml").read_text(encoding="utf-8")
            self.assertNotIn("build:", compose)
            self.assertNotIn("container_name:", compose)
            self.assertIn("image: ceres-care/backend:0.1.0-teste", compose)
            self.assertIn("pull_policy: never", compose)
            self.assertNotIn(b"\r", (destino / "servidor.sh").read_bytes())

    def test_versao_nao_pode_injetar_comandos_ou_caminhos(self):
        for valor in ("../fora", "v1;comando", "1.0.0\nlinha", "1.0.0/fora"):
            with self.assertRaises(ValueError):
                versao_valida(valor)

    def test_manifesto_e_hash_do_executavel_conferem(self):
        with TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            conteudo = raiz / "conteudo"
            conteudo.mkdir()
            preparar_conteudo(ROOT, conteudo, "0.1.0-teste")
            (conteudo / "imagens.tar").write_bytes(b"imagem ficticia, sem banco ou dados")
            saida = raiz / "ceres-care.run"
            resultado = gerar_run(conteudo, saida, "0.1.0-teste", revisao="ficticia", imagens={})
            self.assertEqual(hashlib.sha256(saida.read_bytes()).hexdigest(), resultado["sha256"])
            self.assertIn(resultado["sha256"], saida.with_suffix(".run.sha256").read_text())
            manifesto = json.loads((conteudo / "release.json").read_text(encoding="utf-8"))
            self.assertEqual(manifesto["plataforma"], "linux/amd64")
            self.assertIn("imagens.tar", manifesto["arquivos"])

    @unittest.skipUnless(os.environ.get("CNUTRI_TEST_DOCKER") == "1", "Requer imagem Python Linux local")
    def test_linux_verifica_extrai_recusa_sobrescrita_e_detecta_corrupcao(self):
        with TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            conteudo = raiz / "conteudo"
            conteudo.mkdir()
            preparar_conteudo(ROOT, conteudo, "0.1.0-teste")
            (conteudo / "imagens.tar").write_bytes(b"imagem ficticia")
            pacote = raiz / "teste.run"
            gerar_run(conteudo, pacote, "0.1.0-teste", revisao="ficticia", imagens={})
            programa = '''import pathlib, subprocess, tempfile
with tempfile.TemporaryDirectory() as pasta:
    cmd = ['sh', '/teste/teste.run']
    subprocess.run(cmd + ['--verificar'], check=True, capture_output=True)
    destino = pasta + '/instalacao'
    subprocess.run(cmd + ['--extrair', destino], check=True, capture_output=True)
    assert (pathlib.Path(destino) / 'release.json').is_file()
    assert not (pathlib.Path(destino) / '.env').exists()
    assert subprocess.run(cmd + ['--extrair', destino], capture_output=True).returncode != 0
    alterado = pathlib.Path(pasta) / 'alterado.run'
    dados = pathlib.Path('/teste/teste.run').read_bytes()
    alterado.write_bytes(dados[:-1] + bytes([dados[-1] ^ 1]))
    assert subprocess.run(['sh', str(alterado), '--verificar'], capture_output=True).returncode != 0
print('Extração e integridade conferidas no Linux.')
'''
            subprocess.run(["docker", "run", "--rm", "--network", "none", "--mount",
                f"type=bind,source={raiz},target=/teste,readonly", "python:3.12-slim", "python", "-c", programa],
                check=True, capture_output=True, timeout=30)
