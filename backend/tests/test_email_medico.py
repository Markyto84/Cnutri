"""Avisos médicos com dados fictícios; nenhuma conexão com o Google ou impressora."""
import asyncio
from datetime import timedelta
from hashlib import sha256
import json
import os
import smtplib
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import undefer

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.sessoes import emitir_sessao
from app.main import app
from app.models.models import AuditoriaAdministrativa, AvisoEmailPedido, ConfiguracaoEmailUnidade, ContatoEmailPedido, Filial, FormularioConfig, Pedido, Perfil, Usuario
from app.schemas.schemas import PedidoCreate
from app.services.email_medico import ConexaoEmail, ErroEnvioEmail, cifrar_senha, compor_corpos, compor_mensagem, decifrar_senha, transportar_email
from app.services.fila_email import processar_um, recuperar_interrompidos

SENHA_FICTICIA = "abcdefghijklmnop"


class EmailMedicoTest(unittest.IsolatedAsyncioTestCase):
    async def criar_engine(self):
        return create_async_engine("sqlite+aiosqlite:///:memory:")

    async def asyncSetUp(self):
        self.protecao = patch.object(settings, "EMAIL_CREDENCIAIS_CHAVE", Fernet.generate_key().decode())
        self.protecao.start()
        self.engine = await self.criar_engine()
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a, b = Filial(nome="Unidade Fictícia A", codigo_slug="teste-a"), Filial(nome="Unidade Fictícia B", codigo_slug="teste-b")
            db.add_all([a, b]); await db.flush()
            self.a, self.b = a.id, b.id
            for filial in (a, b):
                for tipo in ("MEDICO", "ENFERMAGEM"):
                    db.add(FormularioConfig(filial_id=filial.id, tipo_publico=tipo, esquema_json={"campos": []}))
            self.headers = {}
            for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA"):
                usuario = Usuario(nome="Pessoa Fictícia", nome_usuario=nome.lower(), senha_hash="não utilizada", perfil=Perfil(nome=nome), filiais=[a])
                db.add(usuario); await db.flush()
                token = await emitir_sessao(db, usuario)
                self.headers[nome] = {"Authorization": "Bearer " + token.access_token}
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://teste")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()
        self.protecao.stop()

    def payload(self, **alteracoes):
        return {"tipo_solicitacao": "MEDICO", "solicitante_nome": "Dra. Conceição", "solicitante_identificacao": "CRM FICTÍCIO",
            "solicitante_email": "medica@example.com", **alteracoes}

    async def pedido(self, **alteracoes):
        resposta = await self.client.post("/api/public/teste-a/pedidos", json=self.payload(**alteracoes))
        self.assertEqual(resposta.status_code, 201, resposta.text)
        return resposta.json()["id"]

    async def configurar(self, filial=None, **alteracoes):
        resposta = await self.client.put(f"/api/admin/avisos-email/{filial or self.a}/configuracao", headers=self.headers["ADMIN_TI"],
            json={"modo": "GOOGLE_APP", "remetente": "dietas-a@example.com", "senha_app": SENHA_FICTICIA, "habilitado": True, **alteracoes})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return resposta

    async def pronto(self, pedido_id, rota="publica"):
        caminho = {"publica": f"/api/cozinha/unidades/{self.a}/pedidos/{pedido_id}/status",
            "operacao": f"/api/operacao/unidades/{self.a}/pedidos/{pedido_id}/status", "anterior": f"/api/pedidos/{pedido_id}/status"}[rota]
        headers = {} if rota == "publica" else self.headers["COZINHA"]
        for etapa in ("EM_PREPARO", "PRONTO", "PRONTO"):
            resposta = await self.client.patch(caminho, headers=headers, json={"status": etapa})
            self.assertEqual(resposta.status_code, 200, resposta.text)

    async def aviso(self, pedido_id):
        async with self.sessoes() as db:
            return await db.scalar(select(AvisoEmailPedido).where(AvisoEmailPedido.pedido_id == pedido_id))

    async def test_email_obrigatorio_so_para_medico_e_validacao_sem_dns(self):
        for valor in (None, "", "invalido", "a@example.com,b@example.com", "a@example.com\r\nBcc: b@example.com", "Nome <a@example.com>"):
            resposta = await self.client.post("/api/public/teste-a/pedidos", json=self.payload(solicitante_email=valor))
            self.assertEqual(resposta.status_code, 422, resposta.text)
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(Pedido)), 0)
        paciente = self.payload(tipo_solicitacao="PACIENTE", nome_paciente="Paciente Fictício")
        paciente.pop("solicitante_email")
        self.assertEqual((await self.client.post("/api/public/teste-a/pedidos", json=paciente)).status_code, 201)

    async def test_email_fica_fora_do_painel_publico_e_do_comprovante_de_envio(self):
        chave = str(uuid4())
        resposta = await self.client.post("/api/public/teste-a/pedidos", headers={"Idempotency-Key": chave}, json=self.payload(solicitante_email=" medica@EXAMPLE.COM "))
        self.assertEqual(resposta.status_code, 201, resposta.text)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(ContatoEmailPedido, resposta.json()["id"])).email, "medica@example.com")
        for rota in (f"/api/public/teste-a/solicitacoes/{chave}", f"/api/cozinha/unidades/{self.a}/estado", "/api/public/teste-a/config"):
            r = await self.client.get(rota)
            self.assertNotIn("medica@example.com", r.text)
            self.assertNotIn("dietas-a@example.com", r.text)

    async def test_somente_ti_configura_e_credenciais_nao_voltam_nem_entram_na_auditoria(self):
        for perfil in (None, "NUTRICIONISTA", "COZINHA"):
            r = await self.client.get(f"/api/admin/avisos-email/{self.a}/configuracao", headers=self.headers.get(perfil, {}))
            self.assertIn(r.status_code, (401, 403))
        resposta = await self.configurar()
        self.assertNotIn(SENHA_FICTICIA, resposta.text)
        consulta = await self.client.get(f"/api/admin/avisos-email/{self.a}/configuracao", headers=self.headers["ADMIN_TI"])
        self.assertTrue(consulta.json()["senha_configurada"])
        async with self.sessoes() as db:
            config = await db.scalar(select(ConfiguracaoEmailUnidade).options(undefer(ConfiguracaoEmailUnidade.senha_cifrada)))
            self.assertNotIn(SENHA_FICTICIA, config.senha_cifrada)
            self.assertEqual(decifrar_senha(self.a, config.senha_cifrada), SENHA_FICTICIA)
            with self.assertRaises(HTTPException):
                decifrar_senha(self.b, config.senha_cifrada)
            for auditoria in (await db.scalars(select(AuditoriaAdministrativa))).all():
                self.assertNotIn(SENHA_FICTICIA, json.dumps([auditoria.antes, auditoria.depois]))

    async def test_validacao_de_credenciais_nao_reflete_senha_e_http_remoto_e_recusado(self):
        corpo = {"remetente": "dietas@example.com", "senha_app": "segredo-invalido"}
        r = await self.client.put(f"/api/admin/avisos-email/{self.a}/configuracao", headers=self.headers["ADMIN_TI"], json=corpo)
        self.assertEqual(r.status_code, 422)
        self.assertNotIn("segredo-invalido", r.text)
        r = await self.client.put(f"/api/admin/avisos-email/{self.a}/configuracao", headers={**self.headers["ADMIN_TI"], "Origin": "http://10.0.0.1"},
            json={**corpo, "senha_app": SENHA_FICTICIA})
        self.assertEqual(r.status_code, 400)
        r = await self.client.get(f"/api/admin/avisos-email/{self.a}/configuracao", headers={**self.headers["ADMIN_TI"], "X-Forwarded-Host": "10.0.0.1:5173"},
            extensions={})
        # Esta requisição direta é HTTPS; o acesso HTTP via proxy é verificado abaixo.
        self.assertTrue(r.json()["acesso_seguro"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as remoto:
            r = await remoto.get(f"/api/admin/avisos-email/{self.a}/configuracao", headers={**self.headers["ADMIN_TI"], "X-Forwarded-Host": "10.0.0.1:5173"})
            self.assertFalse(r.json()["acesso_seguro"])

    async def test_trocar_remetente_exige_nova_credencial_e_relay_remove_senha(self):
        await self.configurar()
        url = f"/api/admin/avisos-email/{self.a}/configuracao"
        r = await self.client.put(url, headers=self.headers["ADMIN_TI"], json={"remetente": "outra@example.com", "habilitado": True})
        self.assertEqual(r.status_code, 422)
        r = await self.client.put(url, headers=self.headers["ADMIN_TI"], json={"modo": "GOOGLE_RELAY", "remetente": "dietas-a@example.com", "habilitado": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["senha_configurada"])

    async def test_as_tres_rotas_de_pronto_criam_um_aviso_por_pedido_sem_disparar_smtp_na_requisicao(self):
        await self.configurar()
        with patch("app.services.fila_email.transportar_email") as transporte:
            for rota in ("publica", "operacao", "anterior"):
                pedido_id = await self.pedido()
                await self.pronto(pedido_id, rota)
                aviso = await self.aviso(pedido_id)
                self.assertEqual(aviso.estado, "PENDENTE")
                self.assertEqual(aviso.destinatario, "medica@example.com")
            transporte.assert_not_called()
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(AvisoEmailPedido)), 3)

    async def test_fila_envia_uma_vez_e_usa_a_conta_da_unidade(self):
        await self.configurar()
        await self.configurar(filial=self.b, remetente="dietas-b@example.com")
        pedido_id = await self.pedido()
        await self.pronto(pedido_id)
        with patch("app.services.fila_email.transportar_email") as transporte:
            self.assertTrue(await processar_um(self.sessoes))
            self.assertFalse(await processar_um(self.sessoes))
            transporte.assert_called_once()
            conexao, mensagem = transporte.call_args.args
            self.assertEqual(conexao.remetente, "dietas-a@example.com")
            self.assertEqual(str(mensagem["To"]), "medica@example.com")
            self.assertIn("está a caminho", mensagem.get_body(preferencelist=("plain",)).get_content())
        aviso = await self.aviso(pedido_id)
        self.assertEqual(aviso.estado, "ENVIADO")
        self.assertIsNotNone(aviso.enviado_em)

    async def test_falha_recuperavel_repete_e_incerto_exige_conferencia(self):
        await self.configurar()
        pedido_id = await self.pedido(); await self.pronto(pedido_id)
        with patch("app.services.fila_email.transportar_email", side_effect=ErroEnvioEmail("Sem conexão", repetir=True)):
            await processar_um(self.sessoes)
        aviso = await self.aviso(pedido_id)
        self.assertEqual(aviso.estado, "PENDENTE")
        async with self.sessoes() as db:
            atual = await db.get(AvisoEmailPedido, aviso.id)
            atual.proxima_tentativa_em = agora_utc() - timedelta(seconds=1); await db.commit()
        with patch("app.services.fila_email.transportar_email", side_effect=ErroEnvioEmail("Conferir recebimento", incerto=True)):
            await processar_um(self.sessoes)
        self.assertEqual((await self.aviso(pedido_id)).estado, "INCERTO")
        r = await self.client.post(f"/api/admin/avisos-email/{self.a}/avisos/{aviso.id}/reenviar", headers=self.headers["ADMIN_TI"], json={})
        self.assertEqual(r.status_code, 409)
        r = await self.client.post(f"/api/admin/avisos-email/{self.a}/avisos/{aviso.id}/reenviar", headers=self.headers["ADMIN_TI"], json={"confirmar_risco_duplicidade": True})
        self.assertEqual(r.status_code, 200, r.text)

    async def test_cancelado_entregue_e_expirado_nao_disparam_aviso_atrasado(self):
        await self.configurar()
        for status in ("CANCELADO", "ENTREGUE", "PRONTO"):
            pedido_id = await self.pedido(); await self.pronto(pedido_id)
            async with self.sessoes() as db:
                pedido = await db.get(Pedido, pedido_id); pedido.status = status
                if status == "PRONTO":
                    aviso = await db.scalar(select(AvisoEmailPedido).where(AvisoEmailPedido.pedido_id == pedido_id))
                    aviso.expira_em = agora_utc() - timedelta(seconds=1)
                await db.commit()
            with patch("app.services.fila_email.transportar_email") as transporte:
                await processar_um(self.sessoes); transporte.assert_not_called()
            self.assertEqual((await self.aviso(pedido_id)).estado, "EXPIRADO" if status == "PRONTO" else "CANCELADO")

    async def test_unidade_desativada_nao_dispara_e_pedidos_anteriores_seguem_sem_email(self):
        pedido_id = await self.pedido(); await self.pronto(pedido_id)
        self.assertEqual((await self.aviso(pedido_id)).estado, "DESATIVADO")
        async with self.sessoes() as db:
            antigo = Pedido(filial_id=self.a, tipo_solicitacao="MEDICO", solicitante_nome="Anterior", solicitante_identificacao="CRM", status="PENDENTE")
            db.add(antigo); await db.commit(); antigo_id = antigo.id
        await self.pronto(antigo_id)
        self.assertIsNone(await self.aviso(antigo_id))

    async def test_interrupcao_do_consumidor_e_marcada_para_conferencia(self):
        await self.configurar()
        pedido_id = await self.pedido(); await self.pronto(pedido_id)
        async with self.sessoes() as db:
            aviso = await db.scalar(select(AvisoEmailPedido))
            aviso.estado, aviso.iniciado_em, aviso.reserva = "PROCESSANDO", agora_utc() - timedelta(minutes=4), str(uuid4())
            await db.commit()
        await recuperar_interrompidos(self.sessoes)
        self.assertEqual((await self.aviso(pedido_id)).estado, "INCERTO")

    async def test_falha_ao_enfileirar_desfaz_tambem_a_mudanca_para_pronto(self):
        pedido_id = await self.pedido()
        rota = f"/api/cozinha/unidades/{self.a}/pedidos/{pedido_id}/status"
        await self.client.patch(rota, json={"status": "EM_PREPARO"})
        with patch("app.api.operacao.enfileirar_aviso_pronto", new_callable=AsyncMock, side_effect=RuntimeError("Falha fictícia")):
            with self.assertRaises(RuntimeError):
                await self.client.patch(rota, json={"status": "PRONTO"})
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, pedido_id)).status, "EM_PREPARO")
            self.assertEqual(await db.scalar(select(func.count()).select_from(AvisoEmailPedido)), 0)

    async def test_reenvio_com_comprovante_anterior_ao_campo_email_continua_idempotente(self):
        dados = self.payload(); dados.pop("solicitante_email")
        corpo = PedidoCreate(**dados).model_dump(mode="json"); corpo.pop("solicitante_email")
        resumo = sha256(json.dumps(corpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        chave = str(uuid4())
        async with self.sessoes() as db:
            pedido = Pedido(filial_id=self.a, tipo_solicitacao="MEDICO", solicitante_nome=dados["solicitante_nome"],
                solicitante_identificacao=dados["solicitante_identificacao"], chave_envio=chave, hash_envio=resumo)
            db.add(pedido); await db.commit()
        r = await self.client.post("/api/public/teste-a/pedidos", headers={"Idempotency-Key": chave}, json=dados)
        self.assertEqual(r.status_code, 200, r.text)

    async def test_teste_de_conexao_nao_envia_mensagem(self):
        await self.configurar()
        with patch("app.api.email.transportar_email") as transporte:
            r = await self.client.post(f"/api/admin/avisos-email/{self.a}/testar", headers=self.headers["ADMIN_TI"])
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(len(transporte.call_args.args), 1)


class TransporteEmailTest(unittest.TestCase):
    def setUp(self):
        self.conexao = ConexaoEmail(1, "dietas@example.com", "GOOGLE_APP", SENHA_FICTICIA)
        self.resumo = {"pedido_id": 123, "unidade": "Unidade Fictícia", "solicitante": "Dra. Conceição <script>",
            "itens": [["Refeição", "MAMINHA COM CANELONE"], ["Local de entrega", "TÉRREO - CONFORTO MÉDICO"], ["Observações", "Sem cebola & sem sal"]],
            "pronto_em": "2026-11-06T15:00:00+00:00"}
        self.mensagem = compor_mensagem(self.conexao, "medica@example.com", self.resumo, "<ficticio@example.com>")

    def servidor(self):
        smtp = Mock()
        smtp.mail.return_value = smtp.rcpt.return_value = smtp.data.return_value = smtp.noop.return_value = (250, b"OK")
        return smtp

    def test_resumo_tem_utf8_texto_e_html_escapado_sem_formulario_executavel(self):
        texto, html = compor_corpos(self.resumo)
        self.assertIn("às 12:00", texto)
        self.assertIn("Conceição", texto)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<form", html)
        self.assertEqual(self.mensagem.get_content_type(), "multipart/alternative")

    def test_tls_antes_da_senha_e_falha_ao_fechar_nao_reenvia_mensagem_aceita(self):
        smtp = self.servidor(); smtp.close.side_effect = OSError("Fechamento fictício")
        with patch("app.services.email_medico.smtplib.SMTP", return_value=smtp):
            transportar_email(self.conexao, self.mensagem)
        nomes = [c[0] for c in smtp.method_calls]
        self.assertLess(nomes.index("starttls"), nomes.index("login"))
        self.assertLess(nomes.index("login"), nomes.index("data"))

    def test_queda_apos_data_e_incerta_e_queda_na_conexao_pode_repetir(self):
        smtp = self.servidor(); smtp.data.side_effect = smtplib.SMTPServerDisconnected("fictício")
        with patch("app.services.email_medico.smtplib.SMTP", return_value=smtp), self.assertRaises(ErroEnvioEmail) as erro:
            transportar_email(self.conexao, self.mensagem)
        self.assertTrue(erro.exception.incerto)
        self.assertFalse(erro.exception.repetir)
        with patch("app.services.email_medico.smtplib.SMTP", side_effect=OSError("fictício")), self.assertRaises(ErroEnvioEmail) as erro:
            transportar_email(self.conexao, self.mensagem)
        self.assertTrue(erro.exception.repetir)

    def test_autenticacao_recusada_nao_expoe_resposta_do_servidor(self):
        smtp = self.servidor(); smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, SENHA_FICTICIA.encode())
        with patch("app.services.email_medico.smtplib.SMTP", return_value=smtp), self.assertRaises(ErroEnvioEmail) as erro:
            transportar_email(self.conexao, self.mensagem)
        self.assertNotIn(SENHA_FICTICIA, str(erro.exception))
        smtp.data.assert_not_called()


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer PostgreSQL de teste")
class EmailMedicoPostgresTest(EmailMedicoTest):
    async def criar_engine(self):
        url = os.environ["CNUTRI_TEST_POSTGRES_URL"]
        esquema = "email_" + uuid4().hex
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{esquema}"')
        await motor.dispose()
        self.esquema = esquema
        return create_async_engine(url, connect_args={"server_settings": {"search_path": esquema}})

    async def asyncTearDown(self):
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA "{self.esquema}" CASCADE')
        await super().asyncTearDown()

    async def test_pronto_concorrente_e_consumidores_criam_e_enviam_um_aviso(self):
        await self.configurar()
        pedido_id = await self.pedido()
        rota = f"/api/cozinha/unidades/{self.a}/pedidos/{pedido_id}/status"
        await self.client.patch(rota, json={"status": "EM_PREPARO"})
        respostas = await asyncio.gather(*[self.client.patch(rota, json={"status": "PRONTO"}) for _ in range(4)])
        self.assertTrue(all(r.status_code in (200, 409) for r in respostas))
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(AvisoEmailPedido)), 1)
        with patch("app.services.fila_email.transportar_email") as transporte:
            await asyncio.gather(processar_um(self.sessoes), processar_um(self.sessoes))
            transporte.assert_called_once()
