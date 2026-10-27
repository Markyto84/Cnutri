"""Filipetas completas e integração das duas rotas, sem impressora ou banco reais."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json
from pathlib import Path
from struct import unpack
import unittest
from unittest.mock import patch

import httpx
from PIL import Image, ImageChops, ImageOps
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import criar_token
from app.main import app
from app.models.models import Dieta, Filial, FormularioConfig, Pedido, Perfil, SessaoUsuario, Usuario
from app.services.fila_impressao import processar_um
from app.services.impressora import LARGURA_LINHA, compor_linhas_filipeta, montar_filipeta
from app.services.impressao_raster import (
    ALTURA_BLOCO, LARGURA_PONTOS, LinhaImpressao, codificar_imagem,
    rasterizar_filipeta, renderizar_filipeta,
)

SNAPSHOT = Path(__file__).resolve().parents[2] / "configuracoes/formularios-unidade-havai.json"
ESQUEMAS = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["formularios"]


def texto_impresso(linhas):
    return "\n".join(linha.texto for linha in linhas)


def texto_corrido(buffer):
    return " ".join(texto_impresso(buffer).split())


def decodificar_raster(buffer):
    """Leitor independente do pacote enviado à impressora para conferir seus pixels."""
    assert buffer.startswith(b"\x1b@\x1ba\x00")
    pos, blocos = 5, []
    while buffer[pos:pos + 4] == b"\x1dv0\x00":
        largura, altura = unpack("<HH", buffer[pos + 4:pos + 8])
        inicio, fim = pos + 8, pos + 8 + largura * altura
        assert fim <= len(buffer)
        bits = Image.frombytes("1", (largura * 8, altura), buffer[inicio:fim])
        blocos.append(ImageOps.invert(bits.convert("L")))
        pos = fim
    assert buffer[pos:] == b"\n\n\x1dVB\x00"
    imagem = Image.new("L", (blocos[0].width, sum(bloco.height for bloco in blocos)), 255)
    topo = 0
    for bloco in blocos:
        imagem.paste(bloco, (0, topo))
        topo += bloco.height
    return imagem, blocos


def pedido_medico():
    return Pedido(
        id=101, filial_id=1, tipo_solicitacao="MEDICO",
        solicitante_nome="Dra. Exemplo de Solicitação", solicitante_identificacao="CRM 123456",
        observacoes_alergias="Sem cebola.\nEntregar a refeição bem aquecida e identificar a embalagem.",
        dados_dinamicos={
            "equipe": "Médica", "horario_entrega": "12:30",
            "refeicao": "MAMINHA ASSADA COM CANELONE DE RICOTA E ESPINAFRE",
            "suco": "COM SUCO", "sobremesa": "SOBREMESA DO DIA",
            "local_entrega": "4º ANDAR - REFEITÓRIO",
        },
    )


def pedido_paciente():
    return Pedido(
        id=102, filial_id=1, tipo_solicitacao="PACIENTE",
        solicitante_nome="Enfermeira Exemplo", solicitante_identificacao="COREN 987654",
        leito="OBS-12", prontuario="PR-0000456", nome_paciente="Paciente Fictício da Validação",
        dieta_id=1, observacoes_alergias="Alergia a leite.\nNão enviar derivados de leite, queijo ou manteiga.",
        dados_dinamicos={
            "andar": "3º ANDAR - COLONOSCOPIA/ENDOSCOPIA", "internado_mais_6h": "Não",
            "matricula": "MAT-000789", "data_nascimento": "1958-04-23", "sexo": "FEMININO",
            "refeicao": "ALMOÇO", "para": "Paciente e Acompanhante",
            "cardapio": "FRANGO AO BECHAMEL BATIDO COM PURÊ DE ABOBRINHA", "liquido_espessado": "NÉCTAR",
            "cardapio_acompanhante": "STROGONOFF DE FRANGO ARROZ E BATATA SAUTÉ",
        },
    )


class FilipetaTest(unittest.TestCase):
    def test_medico_inclui_todos_os_campos_e_identifica_o_solicitante(self):
        pedido = pedido_medico()
        buffer = compor_linhas_filipeta(pedido, "Unidade de Teste", ESQUEMAS["MEDICO"])
        texto = texto_corrido(buffer)
        for campo in ESQUEMAS["MEDICO"]["campos"]:
            self.assertIn(campo["rotulo"] + ":", texto)
        for valor in pedido.dados_dinamicos.values():
            self.assertIn(valor, texto)
        self.assertIn("Registro profissional: CRM 123456", texto)
        self.assertEqual(texto.count("Solicitante:"), 1)
        self.assertIn(pedido.solicitante_nome, texto)
        self.assertIn(" ".join(pedido.observacoes_alergias.split()), texto)
        self.assertLess(texto.index("Equipe:"), texto.index("Horário de entrega:"))
        self.assertLess(texto.index("Sobremesa:"), texto.index("Local de entrega:"))

    def test_enfermagem_inclui_dados_operacionais_sem_sexo_e_prontuario(self):
        pedido = pedido_paciente()
        texto = texto_corrido(compor_linhas_filipeta(pedido, "Unidade de Teste", ESQUEMAS["ENFERMAGEM"], "PASTOSA"))
        for campo in ESQUEMAS["ENFERMAGEM"]["campos"]:
            if campo["id"] not in ("sexo", "prontuario"):
                self.assertIn(campo["rotulo"] + ":", texto)
        for chave, valor in pedido.dados_dinamicos.items():
            if chave == "sexo":
                continue
            esperado = "23/04/1958" if chave == "data_nascimento" else valor
            self.assertIn("".join(esperado.split()), "".join(texto.split()))
        for valor in (pedido.nome_paciente, pedido.leito, pedido.solicitante_nome, pedido.solicitante_identificacao):
            self.assertIn(valor, texto)
        for omitido in ("Sexo:", "Prontuário:", pedido.prontuario, "FEMININO"):
            self.assertNotIn(omitido, texto)
        self.assertIn("Tipo de Dieta: PASTOSA", texto)
        self.assertIn(" ".join(pedido.observacoes_alergias.split()), texto)

    def test_rotulos_e_ordem_do_gestor_campos_novos_e_antigos_sem_duplicar(self):
        pedido = pedido_medico()
        pedido.prontuario = "PR-NAO-IMPRIMIR"
        pedido.dados_dinamicos.update({"ramal": "4321", "campo_antigo": "Valor preservado", "sexo": "SEXO-NAO-IMPRIMIR"})
        esquema = {"campos": [
            {"id": "ramal", "rotulo": "Ramal para contato", "tipo": "texto"},
            {"id": "equipe", "rotulo": "Equipe solicitante", "tipo": "radio"},
            {"id": "sexo", "rotulo": "Sexo renomeado", "tipo": "texto"},
            {"id": "prontuario", "rotulo": "Documento renomeado", "tipo": "texto"},
        ]}
        texto = texto_corrido(compor_linhas_filipeta(pedido, "Unidade", esquema))
        self.assertIn("Ramal para contato: 4321", texto)
        self.assertIn("Equipe solicitante: Médica", texto)
        self.assertLess(texto.index("Ramal para contato:"), texto.index("Equipe solicitante:"))
        self.assertIn("Campo antigo: Valor preservado", texto)
        self.assertIn("Suco: COM SUCO", texto)
        self.assertEqual(texto.count("4321"), 1)
        for omitido in ("Sexo renomeado", "Documento renomeado", "PR-NAO-IMPRIMIR", "SEXO-NAO-IMPRIMIR"):
            self.assertNotIn(omitido, texto)

    def test_sem_configuracao_ou_json_legado_nao_perde_campos_fixos(self):
        pedido = pedido_paciente()
        pedido.dados_dinamicos = None
        texto = texto_corrido(compor_linhas_filipeta(pedido, "Unidade", dieta_nome="GERAL"))
        self.assertNotIn("Prontuário:", texto)
        self.assertNotIn("PR-0000456", texto)
        self.assertIn("Nome do Paciente: Paciente Fictício da Validação", texto)
        self.assertIn("Tipo de Dieta: GERAL", texto)
        self.assertNotIn("Horário de entrega:", texto)

    def test_campos_vazios_booleanos_zero_listas_e_objetos(self):
        pedido = pedido_medico()
        pedido.dados_dinamicos.update({"jejum": False, "quantidade": 0, "itens": ["Água", "Chá"], "detalhes": {"Ramal": "9876"}})
        esquema = {"campos": [{"id": "opcional", "rotulo": "Campo opcional", "tipo": "texto"}]}
        texto = texto_corrido(compor_linhas_filipeta(pedido, "Unidade", esquema))
        for trecho in ("Campo opcional: Não informado", "Jejum: Não", "Quantidade: 0", "Itens: Água; Chá", "Detalhes: Ramal: 9876"):
            self.assertIn(trecho, texto)

    def test_quebra_linhas_sem_cortar_palavras_longas_ou_observacoes(self):
        palavra = "X" * 125
        pedido = pedido_paciente()
        pedido.nome_paciente = "Nome extenso " * 15 + "FINAL DO NOME"
        pedido.observacoes_alergias = palavra + "\n" + "Atenção " * 60 + "FINAL DA OBSERVAÇÃO"
        buffer = compor_linhas_filipeta(pedido, "Unidade extensa " * 8, ESQUEMAS["ENFERMAGEM"])
        self.assertTrue(all(len(linha) <= LARGURA_LINHA for linha in texto_impresso(buffer).splitlines()))
        self.assertIn(palavra, "".join(texto_impresso(buffer).split()))
        self.assertIn("FINAL DO NOME", texto_corrido(buffer))
        self.assertIn("FINAL DA OBSERVAÇÃO", texto_corrido(buffer))

    def test_acentos_controles_e_destaque_severo(self):
        pedido = pedido_medico()
        pedido.solicitante_nome = "Conceic\u0327a\u0303o Áéíóú Çãõ º"
        pedido.observacoes_alergias = "Primeira\x1b\x1d\x00\x0c\r\nÚltima"
        buffer = compor_linhas_filipeta(pedido, "Unidade", ESQUEMAS["MEDICO"], severa=True)
        texto = texto_impresso(buffer)
        self.assertIn("Conceição Áéíóú Çãõ º", texto_corrido(buffer))
        self.assertIn("RESTRIÇÃO SEVERA", texto)
        self.assertIn("Primeira\n", texto)
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\x1d", texto)
        self.assertNotIn("\x00", texto)
        self.assertNotIn("?", texto)


class RasterTest(unittest.TestCase):
    def test_pacote_preserva_pixels_polaridade_e_blocos_sem_cortar_a_ultima_linha(self):
        imagem = Image.new("L", (LARGURA_PONTOS, ALTURA_BLOCO * 3 + 9), 255)
        imagem.putpixel((0, 0), 0)
        imagem.putpixel((25, ALTURA_BLOCO), 0)
        imagem.putpixel((LARGURA_PONTOS - 1, imagem.height - 1), 0)
        reconstruida, blocos = decodificar_raster(codificar_imagem(imagem))
        self.assertEqual([bloco.height for bloco in blocos], [128, 128, 128, 9])
        self.assertIsNone(ImageChops.difference(imagem, reconstruida).getbbox())

    def test_acentos_sao_desenhados_com_glifos_distintos_sem_remover_o_acento(self):
        for acentuada, base in zip("ãõçáÃÕÇÁ", "aocaAOCA"):
            with self.subTest(letra=acentuada):
                imagem, _ = decodificar_raster(rasterizar_filipeta([LinhaImpressao(acentuada)]))
                simples, _ = decodificar_raster(rasterizar_filipeta([LinhaImpressao(base)]))
                simbolo, _ = decodificar_raster(rasterizar_filipeta([LinhaImpressao("?")]))
                self.assertIsNotNone(ImageChops.difference(imagem, simples).getbbox())
                self.assertIsNotNone(ImageChops.difference(imagem, simbolo).getbbox())
        pedido = pedido_medico()
        pedido.solicitante_nome = "a\u0303o\u0303c\u0327a\u0301"
        linhas = compor_linhas_filipeta(pedido, "Unidade")
        self.assertIn("Solicitante: ãõçá", texto_impresso(linhas))
        decomposto = montar_filipeta(pedido, "Unidade")
        pedido.solicitante_nome = "ãõçá"
        self.assertEqual(decomposto, montar_filipeta(pedido, "Unidade"))

    def test_simbolos_chegam_ao_desenho_e_filipeta_extensa_cabe_no_papel(self):
        pedido = pedido_paciente()
        pedido.observacoes_alergias = "Atenção: ação, maçã, coração, café.\n" * 40 + "FINAL ≤ 10 ± 2"
        linhas = compor_linhas_filipeta(pedido, "Unidade extensa " * 8, ESQUEMAS["ENFERMAGEM"], "PASTOSA", True)
        self.assertIn("FINAL ≤ 10 ± 2", texto_impresso(linhas))
        imagem, blocos = decodificar_raster(montar_filipeta(pedido, "Unidade extensa " * 8, ESQUEMAS["ENFERMAGEM"], "PASTOSA", True))
        esperado = renderizar_filipeta(linhas).convert("1", dither=Image.Dither.NONE).convert("L")
        self.assertIsNone(ImageChops.difference(esperado, imagem).getbbox())
        self.assertTrue(all(bloco.height <= ALTURA_BLOCO for bloco in blocos))
        self.assertIsNone(ImageOps.invert(imagem.crop((0, 0, 6, imagem.height))).getbbox())
        self.assertIsNone(ImageOps.invert(imagem.crop((LARGURA_PONTOS - 6, 0, LARGURA_PONTOS, imagem.height))).getbbox())


class ImpressaoRotasTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            filial = Filial(nome="Unidade Teste", codigo_slug="unidade-teste", ip_impressora="192.0.2.10")
            outra = Filial(nome="Outra Unidade", codigo_slug="outra-unidade")
            perfil = Perfil(nome="COZINHA")
            usuario = Usuario(nome="Operador Teste", nome_usuario="cozinha", email="cozinha@teste.local", senha_hash="não utilizado", perfil=perfil, filiais=[filial])
            db.add_all([filial, outra, usuario])
            await db.flush()
            self.filial_id = filial.id
            for tipo, esquema in ESQUEMAS.items():
                db.add(FormularioConfig(filial_id=filial.id, tipo_publico=tipo, esquema_json=deepcopy(esquema)))
                db.add(FormularioConfig(filial_id=outra.id, tipo_publico=tipo, esquema_json={"campos": [
                    {"id": "equipe", "rotulo": "Rótulo de outra unidade", "tipo": "texto"},
                ]}))
            dieta = Dieta(filial_id=filial.id, nome="PASTOSA", severa=True)
            db.add_all([dieta, Dieta(filial_id=filial.id, nome="GERAL")])
            await db.commit()
            self.dieta_id = dieta.id
            jti = str(uuid4())
            db.add(SessaoUsuario(id=jti, usuario_id=usuario.id, expira_em=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)))
            await db.commit()
            self.headers = {"Authorization": "Bearer " + criar_token(usuario, jti)}

        async def banco_teste():
            async with self.sessoes() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def conferir_envio_e_reimpressao(self, pedido):
        payload = {chave: getattr(pedido, chave) for chave in (
            "tipo_solicitacao", "solicitante_identificacao", "solicitante_nome", "nome_paciente",
            "leito", "prontuario", "dieta_id", "observacoes_alergias", "dados_dinamicos",
        )}
        with (
            patch("app.services.fila_impressao.enviar_filipeta", return_value=None) as imprimir,
            patch("app.services.impressora.rasterizar_filipeta", wraps=rasterizar_filipeta) as desenhar,
        ):
            if payload["tipo_solicitacao"] == "PACIENTE":
                payload["prescricao"] = {"referencia": "Prontuário fictício", "data_hora": "2026-10-20T09:00:00-03:00", "prescritor_nome": "Prescritora Fictícia", "prescritor_registro": "CRN TESTE"}
            resposta = await self.client.post("/api/public/unidade-teste/pedidos", json=payload)
            self.assertEqual(resposta.status_code, 201, resposta.text)
            self.assertNotIn("prontuario", resposta.json())
            async with self.sessoes() as db:
                salvo = await db.get(Pedido, resposta.json()["id"])
                self.assertEqual(salvo.prontuario, payload["prontuario"])
                esperado = dict(payload["dados_dinamicos"])
                if esperado.get("liquido_espessado") == "NÉCTAR":
                    esperado.update(liquido_espessado="Sim", tipo_liquido_espessado="NÉCTAR")
                self.assertEqual(salvo.dados_dinamicos, esperado)
            imprimir.assert_not_called()
            self.assertEqual(resposta.json()["impressao"]["estado"], "PENDENTE")
            await processar_um(self.sessoes)
            imprimir.assert_called_once()
            ip, original = imprimir.call_args.args
            self.assertEqual(ip, "192.0.2.10")
            desenhar.assert_called_once()
            conteudo = texto_corrido(desenhar.call_args.args[0])
            linhas = desenhar.call_args.args[0]
            for omitido in ("Sexo:", "Prontuário:", pedido.prontuario, pedido.dados_dinamicos.get("sexo")):
                if omitido:
                    self.assertNotIn(omitido, conteudo)
            self.assertIn("ENTREGA À RECEPÇÃO", conteudo)
            assinatura = next(i for i, linha in enumerate(linhas) if linha.texto == "Assinatura:")
            data_hora = next(i for i, linha in enumerate(linhas) if linha.texto == "Data e hora:")
            self.assertGreater(assinatura, next(i for i, linha in enumerate(linhas) if linha.texto.startswith("Tipo:")))
            self.assertTrue(all(not linha.texto for linha in linhas[assinatura + 1:assinatura + 4]))
            self.assertLess(assinatura, data_hora)
            self.assertIn("____/____/________  ____:____", texto_impresso(linhas))
            imagem, _ = decodificar_raster(original)
            self.assertEqual(imagem.width, LARGURA_PONTOS)
        with patch("app.services.fila_impressao.enviar_filipeta", return_value=None) as reimprimir:
            repetida = await self.client.post(f"/api/pedidos/{resposta.json()['id']}/reimprimir", headers=self.headers)
            self.assertEqual(repetida.status_code, 202, repetida.text)
            self.assertTrue(repetida.json()["enfileirado"])
            await processar_um(self.sessoes)
            reimprimir.assert_called_once_with(ip, original)
        return conteudo

    async def test_medico_impressao_e_reimpressao_identicas_com_config_da_unidade(self):
        texto = await self.conferir_envio_e_reimpressao(pedido_medico())
        self.assertIn("Equipe: Médica", texto)
        self.assertIn("Horário de entrega: 12:30", texto)
        self.assertIn("Suco: COM SUCO", texto)
        self.assertIn("Sobremesa: SOBREMESA DO DIA", texto)
        self.assertIn("Local de entrega: 4º ANDAR - REFEITÓRIO", texto)
        self.assertNotIn("Rótulo de outra unidade", texto)

    async def test_enfermagem_impressao_e_reimpressao_identicas_com_dieta_e_restricao(self):
        pedido = pedido_paciente()
        pedido.dieta_id = self.dieta_id
        texto = await self.conferir_envio_e_reimpressao(pedido)
        for trecho in ("Tipo de Dieta: PASTOSA", "RESTRIÇÃO SEVERA", "Matrícula: MAT-000789", "Data de Nascimento: 23/04/1958", "Líquido espessado: Sim", "Líquidos disponíveis: NÉCTAR"):
            self.assertIn(trecho, texto)

    async def test_sem_impressora_salva_pedido_e_informa_erro_na_reimpressao(self):
        async with self.sessoes() as db:
            filial = await db.get(Filial, self.filial_id)
            filial.ip_impressora = None
            await db.commit()
        with patch("app.services.fila_impressao.enviar_filipeta") as imprimir:
            resposta = await self.client.post("/api/public/unidade-teste/pedidos", json={
                "tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM 123", "solicitante_nome": "Exemplo",
                "dados_dinamicos": pedido_medico().dados_dinamicos, "observacoes_alergias": "Sem restrições",
            })
            self.assertEqual(resposta.status_code, 201, resposta.text)
            imprimir.assert_not_called()
        repetida = await self.client.post(f"/api/pedidos/{resposta.json()['id']}/reimprimir", headers=self.headers)
        self.assertEqual(repetida.status_code, 202)
        self.assertEqual(repetida.json()["impressao"]["estado"], "FALHA")
        self.assertIn("não configurada", repetida.json()["impressao"]["erro"])


if __name__ == "__main__":
    unittest.main()
