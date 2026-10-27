"""Destinatários e cardápios validados em SQLite isolado, sem impressão real."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.sessoes import emitir_sessao
from app.main import app
from app.models.models import Dieta, Filial, FormularioConfig, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.formulario_paciente import formulario_paciente
from app.services.liquido_espessado import formulario_liquidos
from app.services.impressora import compor_linhas_filipeta

ESQUEMAS = json.loads((Path(__file__).resolve().parents[2] / "configuracoes/formularios-unidade-havai.json").read_text(encoding="utf-8"))["formularios"]
GERAL = ESQUEMAS["ENFERMAGEM"]["campos"][11]["grupos"][0]["opcoes"][0]
PASTOSA = "SOPA CREME DE LEGUMES"


class FormularioAcompanhanteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a = Filial(nome="Unidade fictícia A", codigo_slug="acompanhante-a")
            b = Filial(nome="Unidade fictícia B", codigo_slug="acompanhante-b")
            db.add_all([a, b])
            await db.flush()
            self.a, self.b = a.id, b.id
            for unidade in (a, b):
                for tipo, esquema in ESQUEMAS.items():
                    db.add(FormularioConfig(filial_id=unidade.id, tipo_publico=tipo, esquema_json=deepcopy(esquema)))
            geral, pastosa, outra = (Dieta(filial_id=a.id, nome="GERAL"), Dieta(filial_id=a.id, nome="PASTOSA"), Dieta(filial_id=b.id, nome="GERAL"))
            db.add_all([geral, pastosa, outra])
            gestor = Usuario(nome="Gestora fictícia", nome_usuario="gestora", senha_hash="não utilizado",
                perfil=Perfil(nome="NUTRICIONISTA"), filiais=[a])
            db.add(gestor)
            await db.flush()
            self.geral, self.pastosa, self.outra = geral.id, pastosa.id, outra.id
            self.headers = {"Authorization": "Bearer " + (await emitir_sessao(db, gestor)).access_token}
            await db.commit()
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.rota = "/api/public/acompanhante-a/pedidos"

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_liquido_sim_nao_preserva_opcoes_e_cadastro_original(self):
        config = (await self.client.get("/api/public/acompanhante-a/config")).json()["formularios"]["ENFERMAGEM"]
        principal = next(c for c in config["campos"] if c["id"] == "liquido_espessado")
        lista = next(c for c in config["campos"] if c["id"] == "tipo_liquido_espessado")
        original = next(c for c in ESQUEMAS["ENFERMAGEM"]["campos"] if c["id"] == "liquido_espessado")
        self.assertEqual(principal["opcoes"], ["Sim", "Não"])
        self.assertEqual(lista["opcoes"], original["opcoes"])
        self.assertTrue(lista["obrigatorio"])
        self.assertEqual(lista["exibir_quando"], {"campo": "liquido_espessado", "valor": "Sim"})
        self.assertEqual(formulario_liquidos(config), config)
        async with self.sessoes() as db:
            armazenado = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == self.a, FormularioConfig.tipo_publico == "ENFERMAGEM"))
            self.assertEqual(armazenado.esquema_json, ESQUEMAS["ENFERMAGEM"])

    async def test_liquido_sim_exige_tipo_valido_e_sai_na_cozinha_e_filipeta(self):
        dados = self.dados()
        dados["dados_dinamicos"]["liquido_espessado"] = "Sim"
        for valor in (None, "", "FORA DO CADASTRO"):
            dados["dados_dinamicos"]["tipo_liquido_espessado"] = valor
            r = await self.client.post(self.rota, json=dados)
            self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(await self.totais(), (0, 0))
        dados["dados_dinamicos"]["tipo_liquido_espessado"] = "NÉCTAR"
        r = await self.client.post(self.rota, json=dados)
        self.assertEqual(r.status_code, 201, r.text)
        painel = (await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos", headers=self.headers)).json()
        self.assertEqual(painel[0]["dados_dinamicos"]["tipo_liquido_espessado"], "NÉCTAR")
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, r.json()["id"])
            texto = " ".join(l.texto for l in compor_linhas_filipeta(pedido, "Unidade fictícia", ESQUEMAS["ENFERMAGEM"], "PASTOSA"))
            self.assertIn("Líquido espessado: Sim", texto)
            self.assertIn("Líquidos disponíveis: NÉCTAR", texto)

    async def test_liquido_nao_limpa_tipo_e_cliente_antigo_migra_ao_enviar(self):
        for valor in ("Não", "NÉCTAR"):
            dados = self.dados()
            dados["dados_dinamicos"].update(liquido_espessado=valor, tipo_liquido_espessado="MEL")
            r = await self.client.post(self.rota, json=dados)
            self.assertEqual(r.status_code, 201, r.text)
            salvo = (await self.salvo(r))["dados_dinamicos"]
            self.assertEqual(salvo["liquido_espessado"], "Não" if valor == "Não" else "Sim")
            if valor == "Não":
                self.assertNotIn("tipo_liquido_espessado", salvo)
            else:
                self.assertEqual(salvo["tipo_liquido_espessado"], "NÉCTAR")

    def dados(self, para="Paciente"):
        return {"tipo_solicitacao": "PACIENTE", "solicitante_identificacao": "COREN TESTE",
            "prescricao": {"referencia": "Prontuário fictício", "data_hora": "2026-10-20T09:00:00-03:00", "prescritor_nome": "Prescritora Fictícia", "prescritor_registro": "CRN TESTE"} if para != "Acompanhante" else None,
            "solicitante_nome": "Enfermeira fictícia", "nome_paciente": "Paciente fictício",
            "prontuario": "TESTE", "leito": "OBS-12", "dieta_id": self.pastosa,
            "observacoes_alergias": "Dados fictícios", "dados_dinamicos": {
                "andar": "TÉRREO - OBSERVAÇÃO", "internado_mais_6h": "Não", "matricula": "0000123",
                "sexo": "FEMININO", "refeicao": "ALMOÇO", "para": para, "cardapio": PASTOSA}}

    async def totais(self):
        async with self.sessoes() as db:
            return (await db.scalar(select(func.count()).select_from(Pedido)),
                await db.scalar(select(func.count()).select_from(TrabalhoImpressao)))

    async def salvo(self, resposta):
        r = await self.client.get(f"/api/assistencia/pedidos/{resposta.json()['id']}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["pedido"]

    async def test_config_derivada_em_todas_unidades_preserva_cadastro_e_medico(self):
        for slug in ("acompanhante-a", "acompanhante-b"):
            config = (await self.client.get(f"/api/public/{slug}/config")).json()
            campos = config["formularios"]["ENFERMAGEM"]["campos"]
            ids = [c["id"] for c in campos]
            self.assertEqual(ids[ids.index("cardapio") + 1], "cardapio_acompanhante")
            extra = next(c for c in campos if c["id"] == "cardapio_acompanhante")
            self.assertEqual(extra["dieta_fixa"], "GERAL")
            self.assertEqual(config["formularios"]["MEDICO"], ESQUEMAS["MEDICO"])
        async with self.sessoes() as db:
            armazenado = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == self.a, FormularioConfig.tipo_publico == "ENFERMAGEM"))
            self.assertEqual(armazenado.esquema_json, ESQUEMAS["ENFERMAGEM"])
        self.assertEqual(formulario_paciente({"campos": []}), {"campos": []})
        preparado = formulario_paciente(ESQUEMAS["ENFERMAGEM"])
        self.assertEqual(formulario_paciente(preparado), preparado)

    async def test_paciente_continua_com_dieta_e_cardapio_proprios(self):
        r = await self.client.post(self.rota, json=self.dados())
        self.assertEqual(r.status_code, 201, r.text)
        salvo = await self.salvo(r)
        self.assertEqual(salvo["dieta"]["nome"], "PASTOSA")
        self.assertNotIn("cardapio_acompanhante", salvo["dados_dinamicos"])

    async def test_acompanhante_aceita_geral_e_recusa_dieta_especial_ou_de_outra_unidade(self):
        for dieta in (self.pastosa, self.outra, None):
            dados = self.dados("Acompanhante")
            dados["dieta_id"] = dieta
            with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
                r = await self.client.post(self.rota, json=dados)
                self.assertEqual(r.status_code, 422, r.text)
                transporte.assert_not_called()
        self.assertEqual(await self.totais(), (0, 0))
        dados = self.dados("Acompanhante")
        dados["dieta_id"] = self.geral
        dados["dados_dinamicos"]["cardapio"] = GERAL
        r = await self.client.post(self.rota, json=dados)
        self.assertEqual(r.status_code, 201, r.text)
        salvo = await self.salvo(r)
        self.assertEqual(salvo["dieta_id"], self.geral)
        self.assertEqual(salvo["dados_dinamicos"]["cardapio"], GERAL)

    async def test_ambos_preserva_dieta_paciente_e_cardapio_geral_no_painel_e_filipeta(self):
        dados = self.dados("Paciente e Acompanhante")
        dados["dados_dinamicos"]["cardapio_acompanhante"] = GERAL
        r = await self.client.post(self.rota, json=dados)
        self.assertEqual(r.status_code, 201, r.text)
        salvo = await self.salvo(r)
        self.assertEqual(salvo["dieta_id"], self.pastosa)
        self.assertEqual(salvo["dados_dinamicos"]["cardapio"], PASTOSA)
        painel = (await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos", headers=self.headers)).json()
        self.assertEqual(painel[0]["dados_dinamicos"]["cardapio_acompanhante"], GERAL)
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, r.json()["id"])
            linhas = compor_linhas_filipeta(pedido, "Unidade fictícia", ESQUEMAS["ENFERMAGEM"], "PASTOSA")
            texto = " ".join(l.texto for l in linhas)
            self.assertIn("Cardápio do acompanhante:", texto)
            self.assertIn("".join(GERAL.split()), "".join(texto.split()))
        self.assertEqual(await self.totais(), (1, 1))

    async def test_ambos_exige_segundo_cardapio_e_nao_aceita_opcao_da_dieta_paciente(self):
        for valor in (None, "", PASTOSA, "Opção antiga"):
            dados = self.dados("Paciente e Acompanhante")
            if valor is not None:
                dados["dados_dinamicos"]["cardapio_acompanhante"] = valor
            r = await self.client.post(self.rota, json=dados)
            self.assertEqual(r.status_code, 422, r.text)
            self.assertIn("Cardápio do acompanhante", r.text)
        self.assertEqual(await self.totais(), (0, 0))

    async def test_campo_oculto_nao_pode_ser_injetado_em_paciente_ou_acompanhante(self):
        for para in ("Paciente", "Acompanhante"):
            dados = self.dados(para)
            dados["dados_dinamicos"]["cardapio_acompanhante"] = GERAL
            if para == "Acompanhante":
                dados["dieta_id"] = self.geral
                dados["dados_dinamicos"]["cardapio"] = GERAL
            r = await self.client.post(self.rota, json=dados)
            self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(await self.totais(), (0, 0))

    async def test_sem_geral_ativa_ou_sem_grupo_bloqueia_acompanhante_sem_afetar_paciente(self):
        async with self.sessoes() as db:
            (await db.get(Dieta, self.geral)).ativa = False
            await db.commit()
        dados = self.dados("Paciente e Acompanhante")
        dados["dados_dinamicos"]["cardapio_acompanhante"] = GERAL
        self.assertEqual((await self.client.post(self.rota, json=dados)).status_code, 422)
        async with self.sessoes() as db:
            (await db.get(Dieta, self.geral)).ativa = True
            config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == self.a, FormularioConfig.tipo_publico == "ENFERMAGEM"))
            esquema = deepcopy(config.esquema_json)
            next(c for c in esquema["campos"] if c["id"] == "cardapio")["grupos"].pop(0)
            config.esquema_json = esquema
            await db.commit()
        for para in ("Acompanhante", "Paciente e Acompanhante"):
            dados = self.dados(para)
            if para == "Acompanhante":
                dados["dieta_id"] = self.geral
            self.assertEqual((await self.client.post(self.rota, json=dados)).status_code, 422)
        self.assertEqual(await self.totais(), (0, 0))
        self.assertEqual((await self.client.post(self.rota, json=self.dados())).status_code, 201)

    async def test_edicao_do_grupo_geral_pelo_gestor_atualiza_ambos_os_cardapios(self):
        rota = f"/api/gestao/formularios/{self.a}/ENFERMAGEM"
        atual = (await self.client.get(rota, headers=self.headers)).json()
        esquema = deepcopy(atual["esquema_json"])
        next(c for c in esquema["campos"] if c["id"] == "cardapio")["grupos"][0]["opcoes"] = ["NOVO CARDÁPIO GERAL"]
        r = await self.client.put(rota, headers=self.headers, json={"esquema_json": esquema, "versao": atual["atualizado_em"]})
        self.assertEqual(r.status_code, 200, r.text)
        config = (await self.client.get("/api/public/acompanhante-a/config")).json()["formularios"]["ENFERMAGEM"]
        self.assertEqual(next(c for c in config["campos"] if c["id"] == "cardapio_acompanhante")["grupos"][0]["opcoes"], ["NOVO CARDÁPIO GERAL"])
        dados = self.dados("Paciente e Acompanhante")
        dados["dados_dinamicos"]["cardapio_acompanhante"] = GERAL
        self.assertEqual((await self.client.post(self.rota, json=dados)).status_code, 422)
        dados["dados_dinamicos"]["cardapio_acompanhante"] = "NOVO CARDÁPIO GERAL"
        self.assertEqual((await self.client.post(self.rota, json=dados)).status_code, 201)
        dados = self.dados("Acompanhante")
        dados["dieta_id"] = self.geral
        dados["dados_dinamicos"]["cardapio"] = "NOVO CARDÁPIO GERAL"
        self.assertEqual((await self.client.post(self.rota, json=dados)).status_code, 201)
