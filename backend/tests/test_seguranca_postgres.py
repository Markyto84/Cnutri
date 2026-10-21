"""Redefinição concorrente de senha em schema PostgreSQL exclusivo, sem contas reais."""
import asyncio
import os
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import hash_senha, verificar_senha
from app.main import app
from app.models.models import Filial, FormularioConfig, ImpressoraEtiqueta, Pedido, Perfil, TrabalhoImpressao, Usuario
from sqlalchemy import func, update
from app.services.fila_impressao import processar_um

SENHA = "TesteSeguro@123"
NOVA = "TempNova@12"


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer PostgreSQL de teste")
class ConcorrenciaSenhaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.environ["CNUTRI_TEST_POSTGRES_URL"]
        self.schema = "teste_seguranca_" + uuid4().hex
        self.admin_engine = create_async_engine(url)
        async with self.admin_engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self.engine = create_async_engine(url, connect_args={"server_settings": {"search_path": self.schema}})
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            perfil = Perfil(nome="ADMIN_TI")
            usuario = Usuario(nome="Pessoa Fictícia", nome_usuario="pessoa", perfil=perfil, senha_hash=hash_senha(SENHA))
            db.add(usuario)
            await db.commit()
            self.id = usuario.id
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()
        async with self.admin_engine.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.admin_engine.dispose()

    async def conferir_corrida(self, troca):
        cabecalho = {}
        if troca:
            token = (await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).json()["access_token"]
            cabecalho = {"Authorization": "Bearer " + token}
        consulta = asyncio.Event()
        def lendo_senha(_conn, _cursor, statement, _parameters, _context, _many):
            if "FROM usuarios" in statement and ("lower(usuarios.nome_usuario)" in statement or "usuarios.nome_usuario" not in statement):
                consulta.set()
        async with self.sessoes() as redefinicao:
            usuario = await redefinicao.scalar(select(Usuario).where(Usuario.id == self.id).with_for_update())
            usuario.senha_hash = hash_senha(NOVA)
            await redefinicao.flush()
            event.listen(self.engine.sync_engine, "before_cursor_execute", lendo_senha)
            tarefa = None
            try:
                with patch("app.api.auth.verificar_senha", wraps=verificar_senha) as conferir:
                    if troca:
                        tarefa = asyncio.create_task(self.client.post("/api/auth/senha", headers=cabecalho, json={"senha_atual": SENHA, "nova_senha": "Escolha@123"}))
                    else:
                        tarefa = asyncio.create_task(self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA}))
                    await asyncio.wait_for(consulta.wait(), 5)
                    await asyncio.sleep(0.05)  # permite a segunda conexão chegar ao bloqueio da linha.
                    self.assertFalse(conferir.called, "Verificou a senha antiga durante uma redefinição em curso")
                    await redefinicao.commit()
                    resposta = await asyncio.wait_for(tarefa, 5)
                    self.assertEqual(resposta.status_code, 400 if troca else 401, resposta.text)
            finally:
                event.remove(self.engine.sync_engine, "before_cursor_execute", lendo_senha)
                if tarefa and not tarefa.done():
                    tarefa.cancel()
                    await asyncio.gather(tarefa, return_exceptions=True)
        async with self.sessoes() as db:
            self.assertTrue(verificar_senha(NOVA, (await db.get(Usuario, self.id)).senha_hash))

    async def test_login_aguarda_redefinicao_e_recusa_senha_antiga(self):
        await self.conferir_corrida(troca=False)

    async def test_troca_nao_sobrescreve_redefinicao_com_base_em_senha_antiga(self):
        await self.conferir_corrida(troca=True)

    async def preparar_pedidos(self):
        async with self.sessoes() as db:
            filial = Filial(nome="Fictícia", codigo_slug="teste", ip_impressora="192.0.2.10")
            db.add(filial)
            await db.flush()
            db.add(FormularioConfig(filial_id=filial.id, tipo_publico="MEDICO", esquema_json={"campos": []}))
            await db.commit()
        return {"tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM TESTE", "solicitante_nome": "Profissional Fictício"}

    async def test_envios_simultaneos_com_mesma_chave_criam_um_pedido_e_um_trabalho(self):
        payload = await self.preparar_pedidos()
        chave = str(uuid4())
        respostas = await asyncio.gather(*(self.client.post("/api/public/teste/pedidos", headers={"Idempotency-Key": chave}, json=payload) for _ in range(2)))
        self.assertEqual(sorted(r.status_code for r in respostas), [200, 201], [r.text for r in respostas])
        self.assertEqual(respostas[0].json()["id"], respostas[1].json()["id"])
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(Pedido)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao)), 1)

    async def test_dois_consumidores_nao_enviam_mesma_filipeta_duas_vezes(self):
        payload = await self.preparar_pedidos()
        resposta = await self.client.post("/api/public/teste/pedidos", json=payload)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        with patch("app.services.fila_impressao.enviar_filipeta") as transporte:
            resultados = await asyncio.gather(processar_um(self.sessoes), processar_um(self.sessoes))
            self.assertEqual(sum(resultados), 1)
            transporte.assert_called_once()

    async def test_status_fica_pronto_durante_transmissao_da_etiqueta(self):
        await self.preparar_pedidos()
        async with self.sessoes() as db:
            filial = await db.scalar(select(Filial))
            db.add(ImpressoraEtiqueta(filial_id=filial.id, ip="192.0.2.11"))
            pedido = Pedido(filial_id=filial.id, tipo_solicitacao="PACIENTE", status="PRONTO", nome_paciente="Paciente Fictício",
                solicitante_identificacao="TESTE", dados_dinamicos={"matricula": "0001", "refeicao": "ALMOÇO", "cardapio": "ARROZ E FEIJÃO"})
            db.add(pedido)
            await db.commit()
            pedido_id, filial_id = pedido.id, filial.id
        token = (await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).json()["access_token"]
        r = await self.client.post(f"/api/operacao/unidades/{filial_id}/pedidos/{pedido_id}/etiqueta", headers={"Authorization": "Bearer " + token})
        self.assertEqual(r.status_code, 202, r.text)
        enviando, liberar = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        def transporte(*_args):
            loop.call_soon_threadsafe(enviando.set)
            if not liberar.wait(3):
                raise RuntimeError("Teste não liberou o envio")
        async def entregar():
            async with self.sessoes() as db:
                await db.execute(update(Pedido).where(Pedido.id == pedido_id).values(status="ENTREGUE"))
                await db.commit()
        tarefas = []
        try:
            with patch("app.services.fila_impressao.enviar_filipeta", side_effect=transporte):
                tarefas.append(asyncio.create_task(processar_um(self.sessoes)))
                await asyncio.wait_for(enviando.wait(), 5)
                tarefas.append(asyncio.create_task(entregar()))
                await asyncio.sleep(0.05)
                self.assertFalse(tarefas[1].done(), "A entrega alterou o status durante a transmissão da etiqueta")
                liberar.set()
                await asyncio.wait_for(asyncio.gather(*tarefas), 5)
        finally:
            liberar.set()
            for tarefa in tarefas:
                if not tarefa.done():
                    tarefa.cancel()
            await asyncio.gather(*tarefas, return_exceptions=True)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, pedido_id)).etiqueta["estado"], "ENVIADO")
