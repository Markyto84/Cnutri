"""Fila persistida, repetição de pedidos e falhas de impressão: só dados fictícios, sem rede de impressoras."""
from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import undefer

from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.sessoes import emitir_sessao
from app.main import app
from app.models.models import Filial, FormularioConfig, HistoricoPedido, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.fila_impressao import processar_um, recuperar_interrompidos
from app.services.impressora import ErroEnvioImpressora, enviar_filipeta


class FilaPedidoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a = Filial(nome="Unidade Fictícia", codigo_slug="teste", ip_impressora="192.0.2.10")
            b = Filial(nome="Unidade Fictícia", codigo_slug="teste-b", ip_impressora="192.0.2.11")
            db.add_all([a, b])
            await db.flush()
            self.a, self.b = a.id, b.id
            for f in (a, b):
                db.add(FormularioConfig(filial_id=f.id, tipo_publico="MEDICO", esquema_json={"campos": [
                    {"id": "observacoes_alergias", "tipo": "texto_longo", "rotulo": "Observações", "obrigatorio": True}]}))
            usuario = Usuario(nome="Operador Fictício", nome_usuario="operador", senha_hash="não utilizada", perfil=Perfil(nome="COZINHA"), filiais=[a, b])
            db.add(usuario)
            await db.flush()
            token = await emitir_sessao(db, usuario)
            self.headers = {"Authorization": "Bearer " + token.access_token}
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    def payload(self):
        return {"tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM FICTÍCIO", "solicitante_nome": "Profissional Fictício", "observacoes_alergias": "Sem restrições"}

    async def enviar(self, chave=None, payload=None, slug="teste"):
        return await self.client.post(f"/api/public/{slug}/pedidos", headers={"Idempotency-Key": chave or str(uuid4())}, json=self.payload() if payload is None else payload)

    async def test_repetir_mesma_tentativa_retoma_pedido_e_nao_duplica_impressao_nem_evento(self):
        chave = str(uuid4())
        with patch("app.api.public_kiosk.gerenciador_ws.transmitir", new_callable=AsyncMock) as evento:
            primeira, repetida = await self.enviar(chave), await self.enviar(chave)
            self.assertEqual(primeira.status_code, 201, primeira.text)
            self.assertEqual(repetida.status_code, 200, repetida.text)
            self.assertEqual(primeira.json()["id"], repetida.json()["id"])
            self.assertEqual(primeira.json()["impressao"]["estado"], "PENDENTE")
            evento.assert_awaited_once()
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(Pedido)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao)), 1)
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            self.assertTrue(await processar_um(self.sessoes))
            self.assertFalse(await processar_um(self.sessoes))
            transporte.assert_called_once()
        consulta = await self.client.get(f"/api/public/teste/solicitacoes/{chave}")
        self.assertEqual(consulta.json()["impressao"]["estado"], "ENVIADO")
        self.assertNotIn("Fictício", consulta.text)
        self.assertEqual((await self.client.get(f"/api/public/teste-b/solicitacoes/{chave}")).status_code, 404)

    async def test_chave_reutilizada_com_dados_diferentes_nao_cria_outro_pedido(self):
        chave = str(uuid4())
        original = await self.enviar(chave)
        resposta = await self.enviar(chave, {**self.payload(), "observacoes_alergias": "Alteração"})
        self.assertEqual(resposta.status_code, 409, resposta.text)
        self.assertEqual(resposta.json()["detail"]["pedido_id"], original.json()["id"])
        # A mesma chave em outra unidade representa outra operação.
        outra = await self.enviar(chave, slug="teste-b")
        self.assertEqual(outra.status_code, 201, outra.text)
        self.assertNotEqual(original.json()["id"], outra.json()["id"])

    async def test_validacao_nao_reserva_chave_e_replay_ignora_mudanca_posterior_do_formulario(self):
        chave = str(uuid4())
        self.assertEqual((await self.enviar(chave, {**self.payload(), "observacoes_alergias": " "})).status_code, 422)
        original = await self.enviar(chave)
        self.assertEqual(original.status_code, 201, original.text)
        async with self.sessoes() as db:
            config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == self.a))
            config.esquema_json = {"campos": [{"id": "novo", "rotulo": "Novo", "tipo": "texto", "obrigatorio": True}]}
            await db.commit()
        self.assertEqual((await self.enviar(chave)).status_code, 200)
        self.assertEqual((await self.enviar()).status_code, 422)

    async def test_falha_de_conexao_tenta_no_maximo_tres_vezes_com_mesmo_documento(self):
        resposta = await self.enviar()
        with patch("app.services.fila_impressao.enviar_filipeta", side_effect=ErroEnvioImpressora()) as transporte:
            for tentativa in range(1, 4):
                self.assertTrue(await processar_um(self.sessoes))
                async with self.sessoes() as db:
                    job = await db.get(TrabalhoImpressao, resposta.json()["impressao"]["id"])
                    self.assertEqual(job.tentativas, tentativa)
                    self.assertEqual(job.estado, "PENDENTE" if tentativa < 3 else "FALHA")
                    if tentativa < 3:
                        self.assertGreater(job.proxima_tentativa_em, agora_utc())
                        job.proxima_tentativa_em = agora_utc() - timedelta(seconds=1)
                        await db.commit()
            self.assertFalse(await processar_um(self.sessoes))
            self.assertEqual(transporte.call_count, 3)
            self.assertEqual(len({chamada.args[1] for chamada in transporte.call_args_list}), 1)

    async def test_envio_parcial_exige_confirmacao_e_cliques_pendentes_nao_duplicam(self):
        resposta = await self.enviar()
        pedido_id = resposta.json()["id"]
        with patch("app.services.fila_impressao.enviar_filipeta", side_effect=ErroEnvioImpressora(incerto=True)) as transporte:
            await processar_um(self.sessoes)
            self.assertFalse(await processar_um(self.sessoes))
            transporte.assert_called_once()
        rota = f"/api/operacao/unidades/{self.a}/pedidos/{pedido_id}/reimprimir"
        self.assertEqual((await self.client.post(rota, headers=self.headers)).status_code, 409)
        nova = await self.client.post(rota, headers=self.headers, json={"confirmar_risco_duplicidade": True})
        repetida = await self.client.post(rota, headers=self.headers)
        self.assertEqual(nova.status_code, 202, nova.text)
        self.assertEqual(nova.json()["impressao"]["id"], repetida.json()["impressao"]["id"])
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao)), 2)

    async def test_reinicio_recupera_envio_abandonado_como_incerto_sem_reimprimir(self):
        resposta = await self.enviar()
        async with self.sessoes() as db:
            job = await db.get(TrabalhoImpressao, resposta.json()["impressao"]["id"])
            job.estado, job.iniciado_em, job.reserva = "PROCESSANDO", agora_utc() - timedelta(minutes=2), str(uuid4())
            await db.commit()
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            await recuperar_interrompidos(self.sessoes)
            self.assertFalse(await processar_um(self.sessoes))
            transporte.assert_not_called()
        async with self.sessoes() as db:
            self.assertEqual((await db.get(TrabalhoImpressao, resposta.json()["impressao"]["id"])).estado, "INCERTO")

    async def test_pedido_cancelado_e_impressora_ausente_nao_disparam_transporte(self):
        pedido = (await self.enviar()).json()
        async with self.sessoes() as db:
            (await db.get(Pedido, pedido["id"])).status = "CANCELADO"
            (await db.get(Filial, self.a)).ip_impressora = None
            await db.commit()
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            await processar_um(self.sessoes)
            nova = await self.enviar()
            self.assertEqual(nova.status_code, 201, nova.text)
            self.assertEqual(nova.json()["impressao"]["estado"], "FALHA")
            self.assertFalse(await processar_um(self.sessoes))
            transporte.assert_not_called()

    async def test_falha_de_preparacao_permanece_visivel_sem_historico_de_envio(self):
        pedido = (await self.enviar()).json()
        with patch("app.services.fila_impressao.montar_filipeta_configurada", side_effect=RuntimeError("Falha simulada")), patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            await processar_um(self.sessoes)
            transporte.assert_not_called()
        async with self.sessoes() as db:
            job = await db.get(TrabalhoImpressao, pedido["impressao"]["id"])
            self.assertEqual(job.estado, "FALHA")
            self.assertNotIn("simulada", job.erro)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido)), 0)


class TransporteTest(unittest.TestCase):
    def test_falha_antes_da_conexao_e_segura_para_retry(self):
        with patch("app.services.impressora.socket.create_connection", side_effect=OSError):
            with self.assertRaises(ErroEnvioImpressora) as erro:
                enviar_filipeta("192.0.2.10", b"teste")
        self.assertFalse(erro.exception.incerto)

    def test_falha_durante_sendall_e_marcada_como_incerta(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        sock.sendall.side_effect = OSError
        with patch("app.services.impressora.socket.create_connection", return_value=sock):
            with self.assertRaises(ErroEnvioImpressora) as erro:
                enviar_filipeta("192.0.2.10", b"teste")
        self.assertTrue(erro.exception.incerto)
