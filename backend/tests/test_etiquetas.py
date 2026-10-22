"""Etiquetas de refeições prontas: dados fictícios, impressoras simuladas e banco isolado."""
from io import BytesIO
from types import SimpleNamespace
import re
import unittest
from unittest.mock import patch

import httpx
from PIL import Image, ImageChops, ImageDraw, ImageOps
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.sessoes import emitir_sessao
from app.main import app
from app.models.models import Dieta, Filial, HistoricoPedido, ImpressoraEtiqueta, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.etiquetas import campos_etiqueta, codificar_etiqueta, marca_dagua, renderizar_etiqueta
from app.services.fila_impressao import enfileirar, processar_um
from app.services.impressora import ErroEnvioImpressora


def exemplo():
    return SimpleNamespace(nome_paciente="João da Conceição", leito="OBS-12", dieta=SimpleNamespace(nome="BRANDA"),
        dados_dinamicos={"matricula": "00000123", "data_nascimento": "1985-04-09", "andar": "4º ANDAR",
            "refeicao": "ALMOÇO", "cardapio": "FRANGO AO MOLHO, ARROZ E FEIJÃO"})


class LayoutEtiquetaTest(unittest.TestCase):
    def test_sete_campos_na_ordem_com_data_dieta_acento_matricula_e_geometria(self):
        campos = campos_etiqueta(exemplo(), SimpleNamespace(nome="Hospital São João"))
        self.assertEqual(campos, [("Unidade", "Hospital São João"), ("Matrícula", "00000123"),
            ("Nome", "João da Conceição"), ("Data de nascimento", "09/04/1985"),
            ("Dieta", "BRANDA"), ("Andar", "4º ANDAR"), ("Leito", "OBS-12")])
        for dpi in (203, 300):
            imagem = renderizar_etiqueta(campos, dpi)
            self.assertEqual(imagem.size, (round(89 * dpi / 25.4), round(36 * dpi / 25.4)))
            self.assertIsNotNone(ImageOps.invert(imagem).getbbox())
        sem_acento = [(chave, valor.replace("João", "Joao")) for chave, valor in campos]
        self.assertIsNotNone(ImageChops.difference(renderizar_etiqueta(campos), renderizar_etiqueta(sem_acento)).getbbox())

    def test_dados_antigos_ausentes_e_nascimento_ja_formatado(self):
        pedido = SimpleNamespace(nome_paciente=None, dados_dinamicos=None)
        campos = campos_etiqueta(pedido, SimpleNamespace(nome="Unidade"))
        self.assertEqual(len(campos), 7)
        self.assertTrue(all(valor == "Não informado" for _, valor in campos[1:]))
        pedido.dados_dinamicos = {"data_nascimento": "09/04/1985"}
        self.assertEqual(dict(campos_etiqueta(pedido, SimpleNamespace(nome="Unidade")))["Data de nascimento"], "09/04/1985")
        renderizar_etiqueta(campos)

    def test_rodape_reservado_e_marca_dagua_suave_sobrevive_ao_monocromatico(self):
        campos = campos_etiqueta(exemplo(), SimpleNamespace(nome="Hospital São João"))
        for dpi in (203, 300):
            with self.subTest(dpi=dpi):
                marca = marca_dagua(dpi)
                self.assertEqual(set(marca.tobytes()), {0, 255})
                pretos = marca.histogram()[0]
                self.assertGreater(pretos, 100)
                self.assertLess(pretos / (marca.width * marca.height), 0.2)
                with patch("app.services.etiquetas.marca_dagua", return_value=Image.new("L", marca.size, 255)):
                    sem_marca = renderizar_etiqueta(campos, dpi)
                desenho_texto = ImageDraw.ImageDraw.text
                with patch.object(ImageDraw.ImageDraw, "text", autospec=True, side_effect=desenho_texto) as textos:
                    imagem = renderizar_etiqueta(campos, dpi)
                self.assertEqual(textos.call_args.args[2], "CONSUMO IMEDIATO")
                self.assertIsNotNone(ImageChops.difference(imagem, sem_marca).getbbox())
                altura_rodape = round(4.5 * dpi / 25.4)
                caixa = (0, imagem.height - altura_rodape, imagem.width, imagem.height)
                self.assertIsNone(ImageChops.difference(imagem.crop(caixa), sem_marca.crop(caixa)).getbbox())
                self.assertIsNone(ImageChops.difference(imagem, imagem.convert("1", dither=Image.Dither.NONE).convert("L")).getbbox())

    def test_zpl_e_tspl_reconstituem_os_mesmos_pixels_com_polaridades_proprias(self):
        imagem = renderizar_etiqueta(campos_etiqueta(exemplo(), SimpleNamespace(nome="Unidade Teste")))
        zpl = codificar_etiqueta(imagem, "ZPL")
        achado = re.search(rb"\^GFA,(\d+),(\d+),(\d+),([0-9A-F]+)\^FS", zpl)
        self.assertIsNotNone(achado)
        total, total_imagem, largura = map(int, achado.groups()[:3])
        dados = bytes.fromhex(achado.group(4).decode())
        self.assertEqual(total, len(dados))
        self.assertEqual(total, total_imagem)
        decodificada = ImageOps.invert(Image.frombytes("1", (largura * 8, imagem.height), dados).convert("L"))
        self.assertIsNone(ImageChops.difference(imagem.convert("1", dither=Image.Dither.NONE).convert("L"), decodificada.crop((0, 0, imagem.width, imagem.height))).getbbox())
        tspl = codificar_etiqueta(imagem, "TSPL", 3)
        comando = re.search(rb"BITMAP 0,0,(\d+),(\d+),0,", tspl)
        inicio = comando.end()
        dados_tspl = tspl[inicio:inicio + total]
        self.assertEqual(dados_tspl, bytes(b ^ 255 for b in dados))
        self.assertIn(b"SIZE 89 mm,36 mm\r\nGAP 3 mm", tspl)
        self.assertTrue(tspl.endswith(b"\r\nPRINT 1,1\r\n"))
        self.assertIn(b"^PQ1,0,1,N^XZ", zpl)

    def test_texto_longo_nao_e_cortado_e_entradas_nao_injetam_comandos(self):
        pedido = exemplo()
        pedido.dieta.nome = "^XZ\x1b\r\n" + "DIETA " * 300
        campos = campos_etiqueta(pedido, SimpleNamespace(nome="Hospital"))
        self.assertNotIn("\x1b", str(campos))
        with self.assertRaisesRegex(ValueError, "nenhum texto será cortado"):
            renderizar_etiqueta(campos)
        pedido.dieta.nome = "^XZ ~JA ação"
        pacote = codificar_etiqueta(renderizar_etiqueta(campos_etiqueta(pedido, SimpleNamespace(nome="Hospital"))))
        self.assertEqual(pacote.count(b"^XZ"), 1)


class EtiquetaApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            filial = Filial(nome="Hospital São João", codigo_slug="teste", ip_impressora="192.0.2.10")
            outra = Filial(nome="Outra Unidade", codigo_slug="outra")
            db.add_all([filial, outra])
            await db.flush()
            self.a, self.b = filial.id, outra.id
            dieta = Dieta(filial_id=self.a, nome="BRANDA")
            db.add(dieta)
            await db.flush()
            self.tokens = {}
            for nome, perfil, unidades in (("admin", "ADMIN_TI", []), ("cozinha", "COZINHA", [filial]),
                ("outro", "NUTRICIONISTA", [outra]), ("copeira", "COPEIRA", [filial])):
                usuario = Usuario(nome=nome, nome_usuario=nome, senha_hash="não utilizada", perfil=Perfil(nome=perfil), filiais=unidades)
                db.add(usuario)
                await db.flush()
                self.tokens[nome] = {"Authorization": "Bearer " + (await emitir_sessao(db, usuario)).access_token}
            db.add(ImpressoraEtiqueta(filial_id=self.a, modelo="Impressora Fictícia", ip="192.0.2.11", porta=9101, protocolo="TSPL"))
            self.pedidos = {}
            for status in ("PENDENTE", "EM_PREPARO", "PRONTO", "ENTREGUE", "CANCELADO"):
                p = Pedido(filial_id=self.a, tipo_solicitacao="PACIENTE", status=status, solicitante_identificacao="TESTE",
                    nome_paciente=exemplo().nome_paciente, dados_dinamicos=exemplo().dados_dinamicos,
                    dieta_id=dieta.id, leito=exemplo().leito)
                db.add(p)
                await db.flush()
                self.pedidos[status] = p.id
            await db.commit()
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.base = f"/api/operacao/unidades/{self.a}/pedidos/{self.pedidos['PRONTO']}/etiqueta"
        self.config = f"/api/admin/filiais/{self.a}/etiquetas"

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_somente_pronto_e_operadores_da_unidade_podem_visualizar_e_enfileirar(self):
        for metodo in (self.client.get, self.client.post):
            self.assertEqual((await metodo(self.base)).status_code, 401)
            for nome in ("outro", "copeira"):
                self.assertEqual((await metodo(self.base, headers=self.tokens[nome])).status_code, 403)
            for status, pedido_id in self.pedidos.items():
                if status == "PRONTO":
                    continue
                r = await metodo(self.base.replace(f"/{self.pedidos['PRONTO']}/", f"/{pedido_id}/"), headers=self.tokens["cozinha"])
                self.assertEqual(r.status_code, 409, r.text)
        png = await self.client.get(self.base, headers=self.tokens["cozinha"])
        self.assertEqual(png.status_code, 200, png.text if png.status_code != 200 else "")
        self.assertIn("no-store", png.headers["cache-control"])
        imagem = Image.open(BytesIO(png.content))
        self.assertEqual(imagem.size, (711, 288))
        esperada = renderizar_etiqueta(campos_etiqueta(exemplo(), SimpleNamespace(nome="Hospital São João")))
        self.assertIsNone(ImageChops.difference(imagem, esperada).getbbox())

    async def test_filas_independentes_sem_duplicar_cliques_e_sem_imprimir_na_requisicao(self):
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, self.pedidos["PRONTO"])
            await enfileirar(db, pedido, await db.get(Filial, self.a))
            await db.commit()
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            a = await self.client.post(self.base, headers=self.tokens["cozinha"])
            b = await self.client.post(self.base, headers=self.tokens["cozinha"])
            self.assertEqual(a.status_code, 202, a.text)
            self.assertEqual(a.json()["impressao"]["id"], b.json()["impressao"]["id"])
            transporte.assert_not_called()
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, self.pedidos["PRONTO"])
            self.assertNotEqual(pedido.impressao["id"], pedido.etiqueta["id"])
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao)), 2)

    async def test_configuracao_fica_no_trabalho_e_o_envio_nao_altera_status_da_refeicao(self):
        await self.client.post(self.base, headers=self.tokens["cozinha"])
        await self.client.patch(self.config, headers=self.tokens["admin"], json={"ip": "192.0.2.12", "protocolo": "ZPL", "resolucao": 300})
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            await processar_um(self.sessoes)
            ip, dados, porta = transporte.call_args.args
            self.assertEqual((ip, porta), ("192.0.2.11", 9101))
            self.assertTrue(dados.startswith(b"SIZE 89 mm,36 mm"))
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, self.pedidos["PRONTO"])
            self.assertEqual(pedido.status, "PRONTO")
            self.assertIsNone(pedido.impressao)
            self.assertEqual(pedido.etiqueta["estado"], "ENVIADO")
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido)), 0)
        publico = await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos")
        self.assertNotIn("00000123", publico.text)
        self.assertNotIn('"matricula"', publico.text)
        self.assertNotIn("1985-04-09", publico.text)
        self.assertNotIn('"data_nascimento"', publico.text)

    async def test_refeicao_entregue_antes_do_processamento_cancela_etiqueta_sem_tcp(self):
        await self.client.post(self.base, headers=self.tokens["cozinha"])
        async with self.sessoes() as db:
            (await db.get(Pedido, self.pedidos["PRONTO"])).status = "ENTREGUE"
            await db.commit()
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            await processar_um(self.sessoes)
            transporte.assert_not_called()
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, self.pedidos["PRONTO"])).etiqueta["estado"], "CANCELADO")

    async def test_transmissao_incerta_exige_conferencia_e_respeita_impressora_propria(self):
        await self.client.post(self.base, headers=self.tokens["cozinha"])
        with patch("app.services.fila_impressao.enviar_filipeta", side_effect=ErroEnvioImpressora(incerto=True)):
            await processar_um(self.sessoes)
        self.assertEqual((await self.client.post(self.base, headers=self.tokens["cozinha"])).status_code, 409)
        r = await self.client.post(self.base, headers=self.tokens["cozinha"], json={"confirmar_risco_duplicidade": True})
        self.assertEqual(r.status_code, 202, r.text)

    async def test_cadastro_de_ip_porta_protocolo_resolucao_e_teste_sem_papel_restritos_a_ti(self):
        self.assertEqual((await self.client.get(self.config, headers=self.tokens["cozinha"])).status_code, 403)
        for dados in ({"ip": "invalido"}, {"porta": 0}, {"protocolo": "ESC/POS"}, {"resolucao": 600}, {"intervalo_mm": 11}):
            self.assertEqual((await self.client.patch(self.config, headers=self.tokens["admin"], json=dados)).status_code, 422)
        dados = {"modelo": "Tally Dascom · Exemplo", "ip": "192.0.2.20", "porta": 9100, "protocolo": "ZPL", "resolucao": 300, "intervalo_mm": 2}
        r = await self.client.patch(self.config, headers=self.tokens["admin"], json=dados)
        self.assertEqual(r.status_code, 200, r.text)
        with patch("app.api.admin.conectar_etiquetas") as conectar:
            self.assertEqual((await self.client.post(self.config + "/testar", headers=self.tokens["admin"])).status_code, 200)
            conectar.assert_called_once_with("192.0.2.20", 9100)
        await self.client.patch(self.config, headers=self.tokens["admin"], json={"ip": None})
        self.assertEqual((await self.client.post(self.base, headers=self.tokens["cozinha"])).status_code, 400)
        self.assertEqual((await self.client.post(self.config + "/testar", headers=self.tokens["admin"])).status_code, 400)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Filial, self.a)).ip_impressora, "192.0.2.10")
