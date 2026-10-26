"""Rastreabilidade, privacidade, versão e impressão com dados fictícios isolados."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from uuid import uuid4

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.migracao_assistencia import migrar_assistencia
from app.core.sessoes import emitir_sessao
from app.core.ws import ConnectionManager
from app.main import app
from app.models.models import Dieta, EventoAssistencial, Filial, FormularioConfig, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.schemas.schemas import PedidoOut

REFERENCIA = {"referencia": "Prontuário externo FICTÍCIO 1", "data_hora": "2026-10-20T09:15:00-03:00",
    "prescritor_nome": "Prescritora Fictícia", "prescritor_registro": "CRN-3 TESTE"}


class AssistenciaTest(unittest.IsolatedAsyncioTestCase):
    async def criar_engine(self):
        return create_async_engine("sqlite+aiosqlite:///:memory:")

    async def asyncSetUp(self):
        self.engine = await self.criar_engine()
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(migrar_assistencia)
            await conn.run_sync(migrar_assistencia)
        async with self.sessoes() as db:
            a, b = Filial(nome="Unidade fictícia A", codigo_slug="teste-a"), Filial(nome="Unidade fictícia B", codigo_slug="teste-b")
            db.add_all([a, b])
            await db.flush()
            self.a, self.b = a.id, b.id
            dietas = [Dieta(filial_id=a.id, nome="GERAL"), Dieta(filial_id=a.id, nome="PASTOSA")]
            db.add_all(dietas)
            campos = [{"id": k, "tipo": "texto", "rotulo": k, "obrigatorio": True} for k in ("nome_paciente", "prontuario", "leito")]
            campos += [{"id": "dieta_id", "tipo": "selecao_dietas", "rotulo": "Dieta", "obrigatorio": True},
                {"id": "para", "tipo": "selecao", "rotulo": "Para", "opcoes": ["Paciente", "Acompanhante", "Paciente e Acompanhante"], "obrigatorio": True}]
            db.add(FormularioConfig(filial_id=a.id, tipo_publico="ENFERMAGEM", esquema_json={"campos": campos}))
            db.add(FormularioConfig(filial_id=a.id, tipo_publico="MEDICO", esquema_json={"campos": []}))
            self.tokens, self.usuarios = {}, {}
            for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA"):
                u = Usuario(nome="Nome original " + nome, nome_usuario=nome.lower(), senha_hash="não utilizada",
                    perfil=Perfil(nome=nome), filiais=[a])
                db.add(u)
                await db.flush()
                self.usuarios[nome] = u.id
                self.tokens[nome] = {"Authorization": "Bearer " + (await emitir_sessao(db, u)).access_token}
            self.geral, self.pastosa = [d.id for d in dietas]
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.gestor = self.tokens["NUTRICIONISTA"]

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()
        if hasattr(self, "admin_engine"):
            async with self.admin_engine.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
            await self.admin_engine.dispose()

    def dados(self):
        return {"tipo_solicitacao": "PACIENTE", "solicitante_identificacao": "COREN FICTÍCIO",
            "solicitante_nome": "Solicitante declarada", "nome_paciente": "Paciente PRIVADO",
            "prontuario": "PRONTUARIO PRIVADO", "leito": "101", "dieta_id": self.geral,
            "observacoes_alergias": "Alergia PRIVADA", "dados_dinamicos": {"para": "Paciente"}, "prescricao": deepcopy(REFERENCIA)}

    async def criar(self, headers=None):
        dados = self.dados()
        r = await self.client.post("/api/public/teste-a/pedidos", json=dados, headers=headers)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["id"]

    async def detalhe(self, pedido):
        r = await self.client.get(f"/api/assistencia/pedidos/{pedido}", headers=self.gestor)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def corrigir(self, pedido, versao=1, confirmar=False):
        dados = self.dados()
        dados["dieta_id"] = self.pastosa
        dados["prescricao"]["referencia"] = "Prescrição atualizada FICTÍCIA"
        return await self.client.put(f"/api/assistencia/pedidos/{pedido}", headers=self.gestor,
            json={"versao": versao, "motivo": "Correção conforme prontuário fictício", "pedido": dados, "confirmar_substituicao": confirmar})

    async def test_referencia_obrigatoria_exclusiva_paciente_e_sem_atestado_forjado(self):
        dados = self.dados()
        for referencia in (None, {**REFERENCIA, "situacao": "CONFERIDA"}, {**REFERENCIA, "data_hora": "2026-01-01T12:00:00"},
            {**REFERENCIA, "data_hora": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
            {**REFERENCIA, "prescritor_registro": "  "}):
            r = await self.client.post("/api/public/teste-a/pedidos", json={**dados, "prescricao": referencia})
            self.assertEqual(r.status_code, 422, r.text)
        dados["dados_dinamicos"]["para"] = "Acompanhante"
        dados["prescricao"] = None
        self.assertEqual((await self.client.post("/api/public/teste-a/pedidos", json=dados)).status_code, 201)
        medico = {"tipo_solicitacao": "MEDICO", "solicitante_identificacao": "MATRÍCULA FICTÍCIA", "solicitante_nome": "Profissional Teste"}
        self.assertEqual((await self.client.post("/api/public/teste-a/pedidos", json=medico)).status_code, 201)
        self.assertEqual((await self.client.post("/api/public/teste-a/pedidos", json={**medico, "prescricao": REFERENCIA})).status_code, 422)

    async def test_repeticao_nao_duplica_evento_e_distingue_informado_de_autenticado(self):
        headers = {**self.gestor, "Idempotency-Key": str(uuid4())}
        respostas = [await self.client.post("/api/public/teste-a/pedidos", json=self.dados(), headers=headers) for _ in range(2)]
        self.assertEqual([r.status_code for r in respostas], [201, 200])
        detalhe = await self.detalhe(respostas[0].json()["id"])
        self.assertEqual(len(detalhe["eventos"]), 1)
        evento = detalhe["eventos"][0]
        self.assertEqual(evento["autor_usuario_id"], self.usuarios["NUTRICIONISTA"])
        self.assertEqual(evento["depois"]["solicitante_nome"], "Solicitante declarada")
        self.assertEqual(evento["depois"]["prescricao"]["situacao"], "INFORMADA")
        self.assertNotIn("prescricao", respostas[0].text)

    async def test_publico_http_ws_e_perfis_operacionais_nao_recebem_prontuario_ou_referencia(self):
        pedido = await self.criar()
        for token in (None, self.tokens["COZINHA"], self.tokens["COPEIRA"]):
            r = await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos", headers=token)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn("prescricao", r.text)
            self.assertNotIn("PRONTUARIO PRIVADO", r.text)
            if token is None:
                for segredo in ("Paciente PRIVADO", "Alergia PRIVADA", '"dieta"', '"leito"', '"solicitante_nome"'):
                    self.assertNotIn(segredo, r.text)
            else:
                self.assertIn("Paciente PRIVADO", r.text)
            self.assertEqual(r.headers["cache-control"], "private, no-store")
        for token in (None, self.tokens["COZINHA"], self.tokens["COPEIRA"]):
            self.assertEqual((await self.client.get(f"/api/assistencia/pedidos/{pedido}", headers=token)).status_code, 401 if token is None else 403)
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.b}/pedidos", headers=self.gestor)).status_code, 403)
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos", headers={"Authorization": "Bearer invalido"})).status_code, 401)
        r = await self.client.get(f"/api/pedidos?filial_id={self.a}", headers=self.tokens["COZINHA"])
        self.assertNotIn("prescricao", r.text)
        self.assertNotIn("PRONTUARIO PRIVADO", r.text)

        class Socket:
            async def accept(self, **kwargs): pass
            async def send_json(self, msg): self.msg = msg
        publico, interno = Socket(), Socket()
        manager = ConnectionManager()
        await manager.conectar_publico(self.a, publico)
        await manager.conectar(self.a, interno, self.usuarios["COZINHA"])
        async with self.sessoes() as db:
            p = await db.get(Pedido, pedido)
            await db.refresh(p, attribute_names=["dieta", "trabalhos_impressao"])
            await manager.transmitir(self.a, {"evento": "novo_pedido", "pedido": PedidoOut.model_validate(p).model_dump(mode="json")})
        self.assertNotIn("Paciente PRIVADO", json.dumps(publico.msg))
        self.assertIn("Paciente PRIVADO", json.dumps(interno.msg))
        self.assertNotIn("prescricao", json.dumps(interno.msg))

    async def test_conferencia_correcao_preserva_antes_autor_e_cancela_documentos_antigos(self):
        pedido = await self.criar()
        r = await self.client.post(f"/api/assistencia/pedidos/{pedido}/conferencia", headers=self.gestor, json={"versao": 1})
        self.assertEqual(r.status_code, 200, r.text)
        d = await self.detalhe(pedido)
        self.assertEqual(d["pedido"]["prescricao"]["situacao"], "CONFERIDA")
        self.assertEqual((await self.corrigir(pedido)).status_code, 409)
        for status in ("EM_PREPARO", "PRONTO"):
            r = await self.client.patch(f"/api/operacao/unidades/{self.a}/pedidos/{pedido}/status", headers=self.tokens["COZINHA"], json={"status": status})
            self.assertEqual(r.status_code, 200, r.text)
        async with self.sessoes() as db:
            db.add(TrabalhoImpressao(pedido_id=pedido, tipo_documento="ETIQUETA", estado="PENDENTE"))
            await db.commit()
        r = await self.corrigir(pedido, versao=2)
        self.assertEqual(r.status_code, 200, r.text)
        async with self.sessoes() as db:
            await db.execute(update(Usuario).where(Usuario.id == self.usuarios["NUTRICIONISTA"]).values(nome="Nome alterado depois"))
            await db.commit()
        d = await self.detalhe(pedido)
        self.assertEqual(d["pedido"]["status"], "PENDENTE")
        self.assertIsNone(d["pedido"]["concluido_em"])
        self.assertEqual(d["pedido"]["prescricao"]["situacao"], "INFORMADA")
        evento = d["eventos"][-1]
        self.assertEqual(evento["autor_nome"], "Nome original NUTRICIONISTA")
        self.assertEqual(evento["antes"]["dieta_id"], self.geral)
        self.assertEqual(evento["depois"]["dieta_id"], self.pastosa)
        self.assertEqual(evento["motivo"], "Correção conforme prontuário fictício")
        etapas = [e for e in d["eventos"] if e["acao"] == "ETAPA_ALTERADA"]
        self.assertEqual([e["autor_perfil"] for e in etapas], ["COZINHA", "COZINHA"])
        async with self.sessoes() as db:
            trabalhos = (await db.scalars(select(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido).order_by(TrabalhoImpressao.id))).all()
            self.assertEqual([t.estado for t in trabalhos], ["CANCELADO", "CANCELADO", "FALHA"])

    async def test_correcao_exige_motivo_confirma_documentos_e_respeita_estado(self):
        pedido = await self.criar()
        dados = {"versao": 1, "motivo": "    ", "pedido": self.dados()}
        url = f"/api/assistencia/pedidos/{pedido}"
        self.assertEqual((await self.client.put(url, headers=self.gestor, json=dados)).status_code, 422)
        dados["motivo"] = "Tentativa indevida"
        dados["pedido"]["solicitante_nome"] = "Outro solicitante"
        self.assertEqual((await self.client.put(url, headers=self.gestor, json=dados)).status_code, 422)
        async with self.sessoes() as db:
            job = await db.scalar(select(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido))
            job.estado = "PROCESSANDO"
            await db.commit()
        self.assertEqual((await self.corrigir(pedido)).status_code, 409)
        async with self.sessoes() as db:
            await db.execute(update(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido).values(estado="INCERTO"))
            await db.commit()
        self.assertEqual((await self.corrigir(pedido)).status_code, 409)
        self.assertEqual((await self.corrigir(pedido, confirmar=True)).status_code, 200)
        async with self.sessoes() as db:
            await db.execute(update(Pedido).where(Pedido.id == pedido).values(status="ENTREGUE"))
            await db.commit()
        self.assertEqual((await self.corrigir(pedido, versao=2, confirmar=True)).status_code, 409)

    async def test_historico_anterior_nao_inventa_prescricao_e_isola_unidade(self):
        async with self.sessoes() as db:
            p = Pedido(filial_id=self.b, tipo_solicitacao="PACIENTE", solicitante_identificacao="legado", nome_paciente="Legado")
            db.add(p)
            await db.commit()
            id_legado = p.id
        url = f"/api/assistencia/pedidos/{id_legado}"
        self.assertEqual((await self.client.get(url, headers=self.gestor)).status_code, 403)
        r = await self.client.get(url, headers=self.tokens["ADMIN_TI"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["pedido"]["prescricao"])
        self.assertEqual(r.json()["eventos"], [])


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer PostgreSQL de teste")
class AssistenciaPostgresTest(AssistenciaTest):
    async def criar_engine(self):
        self.schema = "teste_assistencia_" + uuid4().hex
        url = os.environ["CNUTRI_TEST_POSTGRES_URL"]
        self.admin_engine = create_async_engine(url)
        async with self.admin_engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        return create_async_engine(url, connect_args={"server_settings": {"search_path": self.schema}})

    async def test_duas_correcoes_mesma_versao_nao_sobrescrevem_historico(self):
        pedido = await self.criar()
        respostas = await asyncio.gather(self.corrigir(pedido), self.corrigir(pedido))
        self.assertEqual(sorted(r.status_code for r in respostas), [200, 409])
        d = await self.detalhe(pedido)
        self.assertEqual([e["acao"] for e in d["eventos"]], ["SOLICITADO", "PEDIDO_CORRIGIDO"])

    async def test_migracao_aditiva_idempotente_nao_atribui_referencia_ao_legado(self):
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("ALTER TABLE pedidos DROP COLUMN prescricao")
            await conn.exec_driver_sql("ALTER TABLE pedidos DROP COLUMN versao")
            await conn.exec_driver_sql(f"INSERT INTO pedidos (filial_id,tipo_solicitacao,solicitante_identificacao,status,dados_dinamicos) VALUES ({self.a},'PACIENTE','LEGADO','PENDENTE','{{}}')")
            await conn.run_sync(migrar_assistencia)
            await conn.run_sync(migrar_assistencia)
        async with self.sessoes() as db:
            p = await db.scalar(select(Pedido))
            self.assertIsNone(p.prescricao)
            self.assertEqual(p.versao, 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(EventoAssistencial)), 0)
