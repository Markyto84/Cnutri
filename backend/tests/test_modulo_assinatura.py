"""Contrato reutilizável e geração de imagem sem dependência de banco ou entrega."""
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from PIL import Image
from pydantic import ValidationError

from app.modules.assinatura import AssinaturaCreate, VERSAO_CONTRATO, gerar_assinatura_png

ROOT = Path(__file__).resolve().parents[2]
EXEMPLOS = json.loads((ROOT / "frontend/tests/fixtures/assinatura-v1.json").read_text(encoding="utf-8"))


class ModuloAssinaturaTest(unittest.TestCase):
    def test_modulo_funciona_sem_configuracao_de_banco_autenticacao_ou_pedidos(self):
        codigo = "from app.modules.assinatura import AssinaturaCreate, gerar_assinatura_png; import sys; assert 'app.core.database' not in sys.modules; assert 'app.schemas.schemas' not in sys.modules"
        r = subprocess.run([sys.executable, "-c", codigo], cwd=ROOT / "backend", env={**os.environ, "JWT_SECRET": ""}, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_contrato_v1_e_importacoes_anteriores_permanecem_compativeis(self):
        from app.schemas.schemas import AssinaturaCreate as EsquemaAnterior
        from app.services.assinatura import gerar_assinatura_png as FuncaoAnterior
        self.assertEqual(VERSAO_CONTRATO, 1)
        self.assertIs(EsquemaAnterior, AssinaturaCreate)
        self.assertIs(FuncaoAnterior, gerar_assinatura_png)
        for dados in EXEMPLOS["validas"]:
            self.assertEqual(AssinaturaCreate.model_validate(dados).model_dump(), dados)

    def test_renderer_valida_dados_antes_de_gerar_imagem(self):
        for dados in EXEMPLOS["invalidas"]:
            with self.subTest(dados=dados):
                with self.assertRaises(ValidationError):
                    gerar_assinatura_png(dados)
        for coordenada in (float("nan"), float("inf")):
            with self.assertRaises(ValidationError):
                gerar_assinatura_png({"tracos": [[{"x": coordenada, "y": 0}, {"x": 1, "y": 1}]]})

    def test_png_preserva_dimensoes_contraste_e_posicao_do_desenho(self):
        dados = EXEMPLOS["validas"][0]
        imagem = gerar_assinatura_png(dados)
        self.assertEqual(imagem, gerar_assinatura_png(AssinaturaCreate.model_validate(dados)))
        with Image.open(BytesIO(imagem)) as png:
            self.assertEqual(png.format, "PNG")
            self.assertEqual(png.size, (1000, 500))
            self.assertEqual(png.mode, "L")
            self.assertEqual(png.getextrema(), (20, 255))
            self.assertEqual(png.getpixel((0, 0)), 255)
            self.assertEqual(png.getpixel((100, 349)), 20)

    def test_limites_de_tracos_e_pontos_sao_aplicados_no_servidor(self):
        def traco(n):
            return [{"x": 0.8 if i % 2 else 0.2, "y": 0.5} for i in range(n)]
        valido = [traco(1500) for _ in range(5)] + [traco(500)]
        self.assertEqual(sum(map(len, AssinaturaCreate.model_validate({"tracos": valido}).tracos)), 8000)
        for invalido in ([traco(1501)], [traco(2) for _ in range(41)], valido + [traco(2)]):
            with self.assertRaises(ValidationError):
                AssinaturaCreate.model_validate({"tracos": invalido})
