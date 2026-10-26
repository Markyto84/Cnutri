"""Reconciliação condicional, contexto central e isolamento dos canais; dados fictícios."""
from datetime import timedelta
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.sessoes import emitir_sessao
from app.core.ws import ConnectionManager
from app.main import app, ws_cozinha, ws_operacao
from app.models.models import ConfiguracaoOperacional, Filial, Pedido, Perfil, SessaoCopeira, Usuario
from app.services.contexto_operacao import MonitorContexto


class SocketTeste:
    def __init__(self, token=None):
        self.mensagens = []
        self.fechado = None
        self.scope = {"subprotocols": ["cnutri", token] if token else []}
        self.recebidos = iter(["ping"])

    async def accept(self, **kwargs):
        pass

    async def send_json(self, mensagem):
        self.mensagens.append(mensagem)

    async def close(self, code=1000):
        self.fechado = code

    async def receive_text(self):
        try:
            return next(self.recebidos)
        except StopIteration:
            raise RuntimeError("Fim do teste") from None


class SincronizacaoOperacaoTest(unittest.IsolatedAsyncioTestCase):
    async def criar_engine(self):
        return create_async_engine("sqlite+aiosqlite:///:memory:")

    async def asyncSetUp(self):
        self.motor = await self.criar_engine()
        self.sessoes = async_sessionmaker(self.motor, expire_on_commit=False)
        async with self.motor.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a, b = Filial(nome="Unidade A", codigo_slug="a"), Filial(nome="Unidade B", codigo_slug="b")
            admin, copeira, gestor = Perfil(nome="ADMIN_TI"), Perfil(nome="COPEIRA"), Perfil(nome="NUTRICIONISTA")
            db.add_all([a, b, admin, copeira, gestor]); await db.flush()
            pessoas = [Usuario(nome="TI Fictícia", nome_usuario="ti", perfil=admin, senha_hash="INUTILIZAVEL", filiais=[]),
                Usuario(nome="Copeira Privada A", nome_usuario="ana", perfil=copeira, senha_hash="INUTILIZAVEL", filiais=[a]),
                Usuario(nome="Gestor B", nome_usuario="gestor", perfil=gestor, senha_hash="INUTILIZAVEL", filiais=[b])]
            db.add_all(pessoas); await db.flush()
            self.a, self.b, self.ana = a.id, b.id, pessoas[1].id
            db.add(Pedido(filial_id=a.id, tipo_solicitacao="PACIENTE", solicitante_identificacao="COREN PRIVADO", solicitante_nome="Profissional Privada",
                nome_paciente="Paciente Privado", leito="LEITO PRIVADO", status="PRONTO", dados_dinamicos={"matricula": "MATRICULA PRIVADA"}))
            self.tokens = {}
            for p in pessoas:
                self.tokens[p.nome_usuario] = (await emitir_sessao(db, p)).access_token
            await db.commit()

        async def obter_db():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = obter_db
        self.cliente = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.rota = f"/api/operacao/unidades/{self.a}/estado"

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.cliente.aclose()
        await self.motor.dispose()
        if hasattr(self, "admin_engine"):
            async with self.admin_engine.begin() as c:
                await c.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
            await self.admin_engine.dispose()

    def cabecalhos(self, nome="ti", **outros):
        return {"Authorization": "Bearer " + self.tokens[nome], **outros}

    async def test_snapshot_publico_nao_expoe_paciente_ou_copeira(self):
        publico = await self.cliente.get(self.rota)
        self.assertEqual(publico.status_code, 200)
        for texto in ("Paciente Privado", "Copeira Privada", "LEITO PRIVADO", "COREN PRIVADO", "MATRICULA PRIVADA"):
            self.assertNotIn(texto, publico.text)
        self.assertEqual(publico.json()["copeiras"], [])
        interno = await self.cliente.get(self.rota, headers=self.cabecalhos())
        self.assertIn("Paciente Privado", interno.text)
        self.assertIn("Copeira Privada A", interno.text)
        self.assertNotEqual(publico.headers["etag"], interno.headers["etag"])

    async def test_etag_retorna_304_sem_corpo_e_muda_quando_prazo_muda(self):
        primeira = await self.cliente.get(self.rota, headers=self.cabecalhos())
        cabecalhos = self.cabecalhos(**{"If-None-Match": primeira.headers["etag"]})
        igual = await self.cliente.get(self.rota, headers=cabecalhos)
        self.assertEqual(igual.status_code, 304)
        self.assertEqual(igual.content, b"")
        self.assertIn("no-store", igual.headers["cache-control"])
        resposta = await self.cliente.put(f"/api/gestao/alertas/{self.a}", headers=self.cabecalhos(), json={"preparo_minutos": 15, "entrega_minutos": 20})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        nova = await self.cliente.get(self.rota, headers=cabecalhos)
        self.assertEqual(nova.status_code, 200)
        self.assertNotEqual(nova.headers["etag"], primeira.headers["etag"])
        self.assertEqual(nova.json()["alertas"]["preparo_minutos"], 15)

    async def test_etag_nao_contorna_revogacao_acesso_ou_unidade_inativa(self):
        antes = await self.cliente.get(self.rota, headers=self.cabecalhos())
        etag = {"If-None-Match": antes.headers["etag"]}
        self.assertEqual((await self.cliente.get(self.rota, headers=self.cabecalhos("gestor", **etag))).status_code, 403)
        await self.cliente.post("/api/auth/logout", headers=self.cabecalhos())
        self.assertEqual((await self.cliente.get(self.rota, headers=self.cabecalhos(**etag))).status_code, 401)
        async with self.sessoes() as db:
            (await db.get(Filial, self.a)).ativa = False
            await db.commit()
        self.assertEqual((await self.cliente.get(self.rota, headers=etag)).status_code, 404)

    async def test_monitor_faz_tres_leituras_para_varias_telas_e_so_envia_mudancas(self):
        canais = ConnectionManager(); monitor = MonitorContexto()
        internos = [SocketTeste() for _ in range(8)]
        publico = SocketTeste(); outra = SocketTeste()
        for s in internos:
            await canais.conectar(self.a, s, 1)
        await canais.conectar_publico(self.a, publico)
        await canais.conectar(self.b, outra, 3)
        consultas = []
        def contar(conn, cursor, sql, parameters, context, executemany):
            consultas.append(sql)
        event.listen(self.motor.sync_engine, "before_cursor_execute", contar)
        try:
            await monitor.atualizar(self.sessoes, canais)
        finally:
            event.remove(self.motor.sync_engine, "before_cursor_execute", contar)
        self.assertEqual(len(consultas), 3)
        self.assertIn("copeiras", internos[0].mensagens[0])
        self.assertNotIn("copeiras", publico.mensagens[0])
        self.assertEqual(outra.mensagens[0]["copeiras"], [])
        await monitor.atualizar(self.sessoes, canais)
        self.assertEqual(len(internos[0].mensagens), 1)
        async with self.sessoes() as db:
            sessao = await db.scalar(select(SessaoCopeira))
            sessao.presenca_ate = agora_utc() - timedelta(seconds=1)
            db.add(ConfiguracaoOperacional(filial_id=self.a, preparo_minutos=10, entrega_minutos=15))
            await db.commit()
        await monitor.atualizar(self.sessoes, canais)
        self.assertEqual(internos[0].mensagens[-1]["copeiras"], [])
        self.assertEqual(internos[0].mensagens[-1]["alertas"]["entrega_minutos"], 15)
        self.assertNotIn("copeiras", publico.mensagens[-1])
        self.assertEqual(len(outra.mensagens), 1)

    async def test_monitor_encerra_canais_quando_unidade_e_desativada(self):
        canais = ConnectionManager(); monitor = MonitorContexto()
        privado, publico = SocketTeste(), SocketTeste()
        await canais.conectar(self.a, privado, 1); await canais.conectar_publico(self.a, publico)
        async with self.sessoes() as db:
            (await db.get(Filial, self.a)).ativa = False
            await db.commit()
        await monitor.atualizar(self.sessoes, canais)
        self.assertEqual(privado.fechado, 1008)
        self.assertEqual(publico.fechado, 1008)

    async def test_contexto_privado_nao_dispara_mensagem_publica(self):
        canais = ConnectionManager(); privado, publico = SocketTeste(), SocketTeste()
        await canais.conectar(self.a, privado, 1); await canais.conectar_publico(self.a, publico)
        await canais.transmitir_contexto(self.a, {}, {"copeiras": [{"id": 9, "nome": "Fictícia"}], "segredo": "NUNCA"})
        self.assertEqual(len(privado.mensagens), 1)
        self.assertNotIn("segredo", privado.mensagens[0])
        self.assertEqual(publico.mensagens, [])

    async def test_pulso_funciona_no_canal_publico_e_no_autenticado(self):
        publico, privado = SocketTeste(), SocketTeste(self.tokens["ana"])
        with patch("app.main.SessionLocal", self.sessoes):
            await ws_operacao(publico, self.a)
            await ws_cozinha(privado, self.a)
        self.assertEqual(publico.mensagens, [{"evento": "pong"}])
        self.assertEqual(privado.mensagens, [{"evento": "pong"}])


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer PostgreSQL de teste")
class SincronizacaoOperacaoPostgresTest(SincronizacaoOperacaoTest):
    async def criar_engine(self):
        self.schema = "teste_sincronizacao_" + uuid4().hex
        url = os.environ["CNUTRI_TEST_POSTGRES_URL"]
        self.admin_engine = create_async_engine(url)
        async with self.admin_engine.begin() as c:
            await c.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        return create_async_engine(url, connect_args={"server_settings": {"search_path": self.schema}})
