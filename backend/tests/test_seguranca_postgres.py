"""Redefinição concorrente de senha em schema PostgreSQL exclusivo, sem contas reais."""
import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import hash_senha, verificar_senha
from app.main import app
from app.models.models import Perfil, Usuario

SENHA = "TesteSeguro@123"
NOVA = "TemporariaNova@2026"


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
                        tarefa = asyncio.create_task(self.client.post("/api/auth/senha", headers=cabecalho, json={"senha_atual": SENHA, "nova_senha": "EscolhidaPeloUsuario@2026"}))
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
