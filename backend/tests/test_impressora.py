"""Filipetas completas e integração das duas rotas, sem impressora ou banco reais."""
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import criar_token
from app.main import app
from app.models.models import Dieta, Filial, FormularioConfig, Pedido, Perfil, Usuario
from app.services.impressora import LARGURA_LINHA, _centralizar, _esquerda, montar_filipeta

SNAPSHOT = Path(__file__).resolve().parents[2] / "configuracoes/formularios-unidade-havai.json"
ESQUEMAS = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["formularios"]


def texto_impresso(buffer):
    sem_comandos = re.sub(rb"\x1b(?:@|[!t].)", b"", buffer, flags=re.DOTALL)
    return sem_comandos.removesuffix(b"\x1dVB\x00").decode("cp850")


def texto_corrido(buffer):
    return " ".join(texto_impresso(buffer).split())


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
        },
    )


class FilipetaTest(unittest.TestCase):
    def test_medico_inclui_todos_os_campos_e_identifica_o_solicitante(self):
        pedido = pedido_medico()
        buffer = montar_filipeta(pedido, "Unidade de Teste", ESQUEMAS["MEDICO"])
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

    def test_enfermagem_inclui_prontuario_matricula_nascimento_cardapio_e_restricoes(self):
        pedido = pedido_paciente()
        texto = texto_corrido(montar_filipeta(pedido, "Unidade de Teste", ESQUEMAS["ENFERMAGEM"], "PASTOSA"))
        for campo in ESQUEMAS["ENFERMAGEM"]["campos"]:
            self.assertIn(campo["rotulo"] + ":", texto)
        for chave, valor in pedido.dados_dinamicos.items():
            self.assertIn("23/04/1958" if chave == "data_nascimento" else valor, texto)
        for valor in (pedido.nome_paciente, pedido.leito, pedido.prontuario, pedido.solicitante_nome, pedido.solicitante_identificacao):
            self.assertIn(valor, texto)
        self.assertIn("Tipo de Dieta: PASTOSA", texto)
        self.assertIn(" ".join(pedido.observacoes_alergias.split()), texto)

    def test_rotulos_e_ordem_do_gestor_campos_novos_e_antigos_sem_duplicar(self):
        pedido = pedido_medico()
        pedido.dados_dinamicos.update({"ramal": "4321", "campo_antigo": "Valor preservado"})
        esquema = {"campos": [
            {"id": "ramal", "rotulo": "Ramal para contato", "tipo": "texto"},
            {"id": "equipe", "rotulo": "Equipe solicitante", "tipo": "radio"},
        ]}
        texto = texto_corrido(montar_filipeta(pedido, "Unidade", esquema))
        self.assertIn("Ramal para contato: 4321", texto)
        self.assertIn("Equipe solicitante: Médica", texto)
        self.assertLess(texto.index("Ramal para contato:"), texto.index("Equipe solicitante:"))
        self.assertIn("Campo antigo: Valor preservado", texto)
        self.assertIn("Suco: COM SUCO", texto)
        self.assertEqual(texto.count("4321"), 1)

    def test_sem_configuracao_ou_json_legado_nao_perde_campos_fixos(self):
        pedido = pedido_paciente()
        pedido.dados_dinamicos = None
        texto = texto_corrido(montar_filipeta(pedido, "Unidade", dieta_nome="GERAL"))
        self.assertIn("Prontuário: PR-0000456", texto)
        self.assertIn("Nome do Paciente: Paciente Fictício da Validação", texto)
        self.assertIn("Tipo de Dieta: GERAL", texto)
        self.assertNotIn("Horário de entrega:", texto)

    def test_campos_vazios_booleanos_zero_listas_e_objetos(self):
        pedido = pedido_medico()
        pedido.dados_dinamicos.update({"jejum": False, "quantidade": 0, "itens": ["Água", "Chá"], "detalhes": {"Ramal": "9876"}})
        esquema = {"campos": [{"id": "opcional", "rotulo": "Campo opcional", "tipo": "texto"}]}
        texto = texto_corrido(montar_filipeta(pedido, "Unidade", esquema))
        for trecho in ("Campo opcional: Não informado", "Jejum: Não", "Quantidade: 0", "Itens: Água; Chá", "Detalhes: Ramal: 9876"):
            self.assertIn(trecho, texto)

    def test_quebra_linhas_sem_cortar_palavras_longas_ou_observacoes(self):
        palavra = "X" * 125
        texto = "Início " + palavra + "\nFim da observação, sem truncar a última palavra."
        for funcao in (_esquerda, _centralizar):
            with self.subTest(alinhamento=funcao.__name__):
                saida = funcao(texto).decode("cp850")
                self.assertTrue(all(len(linha) <= LARGURA_LINHA for linha in saida.splitlines()))
                self.assertEqual("".join(saida.split()), "".join(texto.split()))
        pedido = pedido_paciente()
        pedido.nome_paciente = "Nome extenso " * 15 + "FINAL DO NOME"
        pedido.observacoes_alergias = "Atenção " * 60 + "FINAL DA OBSERVAÇÃO"
        buffer = montar_filipeta(pedido, "Unidade extensa " * 8, ESQUEMAS["ENFERMAGEM"])
        self.assertTrue(all(len(linha) <= LARGURA_LINHA for linha in texto_impresso(buffer).splitlines()))
        self.assertIn("FINAL DO NOME", texto_corrido(buffer))
        self.assertIn("FINAL DA OBSERVAÇÃO", texto_corrido(buffer))

    def test_acentos_controles_e_destaque_severo(self):
        pedido = pedido_medico()
        pedido.solicitante_nome = "Conceic\u0327a\u0303o Áéíóú Çãõ º"
        pedido.observacoes_alergias = "Primeira\x1b\x1d\x00\x0c\r\nÚltima"
        buffer = montar_filipeta(pedido, "Unidade", ESQUEMAS["MEDICO"], severa=True)
        self.assertTrue(buffer.startswith(b"\x1b@\x1bt\x02"))
        self.assertTrue(buffer.endswith(b"\x1dVB\x00"))
        texto = texto_impresso(buffer)
        self.assertIn("Conceição Áéíóú Çãõ º", texto)
        self.assertIn("RESTRIÇÃO SEVERA", texto)
        self.assertIn("Primeira\n", texto)
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\x1d", texto)
        self.assertNotIn("\x00", texto)
        self.assertNotIn("?", texto)


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
            usuario = Usuario(nome="Operador Teste", email="cozinha@teste.local", senha_hash="não utilizado", perfil=perfil, filiais=[filial])
            db.add_all([filial, outra, usuario])
            await db.flush()
            self.filial_id = filial.id
            for tipo, esquema in ESQUEMAS.items():
                db.add(FormularioConfig(filial_id=filial.id, tipo_publico=tipo, esquema_json=deepcopy(esquema)))
                db.add(FormularioConfig(filial_id=outra.id, tipo_publico=tipo, esquema_json={"campos": [
                    {"id": "equipe", "rotulo": "Rótulo de outra unidade", "tipo": "texto"},
                ]}))
            dieta = Dieta(filial_id=filial.id, nome="PASTOSA", severa=True)
            db.add(dieta)
            await db.commit()
            self.dieta_id = dieta.id
            self.headers = {"Authorization": "Bearer " + criar_token(usuario)}

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
        with patch("app.api.public_kiosk.imprimir_filipeta", return_value=True) as imprimir:
            resposta = await self.client.post("/api/public/unidade-teste/pedidos", json=payload)
            self.assertEqual(resposta.status_code, 201, resposta.text)
            imprimir.assert_called_once()
            ip, original = imprimir.call_args.args
            self.assertEqual(ip, "192.0.2.10")
        with patch("app.api.pedidos.imprimir_filipeta", return_value=True) as reimprimir:
            repetida = await self.client.post(f"/api/pedidos/{resposta.json()['id']}/reimprimir", headers=self.headers)
            self.assertEqual(repetida.status_code, 200, repetida.text)
            self.assertTrue(repetida.json()["impresso"])
            reimprimir.assert_called_once_with(ip, original)
        return texto_corrido(original)

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
        for trecho in ("Tipo de Dieta: PASTOSA", "RESTRIÇÃO SEVERA", "Prontuário: PR-0000456", "Matrícula: MAT-000789", "Data de Nascimento: 23/04/1958", "Líquido espessado: NÉCTAR"):
            self.assertIn(trecho, texto)

    async def test_sem_impressora_salva_pedido_e_informa_erro_na_reimpressao(self):
        async with self.sessoes() as db:
            filial = await db.get(Filial, self.filial_id)
            filial.ip_impressora = None
            await db.commit()
        with patch("app.api.public_kiosk.imprimir_filipeta") as imprimir:
            resposta = await self.client.post("/api/public/unidade-teste/pedidos", json={
                "tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM 123", "solicitante_nome": "Exemplo",
            })
            self.assertEqual(resposta.status_code, 201, resposta.text)
            imprimir.assert_not_called()
        repetida = await self.client.post(f"/api/pedidos/{resposta.json()['id']}/reimprimir", headers=self.headers)
        self.assertEqual(repetida.status_code, 400)


if __name__ == "__main__":
    unittest.main()
