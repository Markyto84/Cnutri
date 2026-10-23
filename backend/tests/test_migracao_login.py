"""Migração PostgreSQL em schema temporário, revertido ao terminar o teste.

Para executar, defina CNUTRI_TEST_POSTGRES_URL com um banco de teste PostgreSQL.
Não acessa usuários de outros schemas e só conecta ao endereço expressamente fornecido.
"""
import os
import re
import unittest
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.login_usuarios import PADRAO_USUARIO, migrar_login_usuarios
from app.core.migracao_seguranca import migrar_seguranca
from app.core.migracao_operacao import migrar_operacao
from app.core.migracao_etiquetas import migrar_etiquetas
from app.core.migracao_ad import migrar_ad


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer CNUTRI_TEST_POSTGRES_URL para testar a migração PostgreSQL")
class MigracaoLoginTest(unittest.IsolatedAsyncioTestCase):
    async def test_migracao_ad_preserva_senhas_vinculos_e_define_contas_locais(self):
        engine = create_async_engine(os.environ["CNUTRI_TEST_POSTGRES_URL"])
        schema = "teste_ad_" + uuid4().hex
        try:
            async with engine.connect() as conn:
                transacao = await conn.begin()
                try:
                    await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                    await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    await conn.exec_driver_sql("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, senha_hash TEXT NOT NULL)")
                    await conn.exec_driver_sql("INSERT INTO usuarios VALUES (1, 'hash-preservado'), (2, 'outro-hash')")
                    await conn.exec_driver_sql("CREATE TABLE vinculos (usuario_id INTEGER REFERENCES usuarios(id))")
                    await conn.exec_driver_sql("INSERT INTO vinculos VALUES (1)")
                    await conn.run_sync(migrar_ad)
                    await conn.run_sync(migrar_ad)
                    registros = (await conn.exec_driver_sql("SELECT id, senha_hash, origem_autenticacao, usuario_ad, ad_object_guid FROM usuarios ORDER BY id")).all()
                    self.assertEqual([tuple(r) for r in registros], [(1, 'hash-preservado', 'LOCAL', None, None), (2, 'outro-hash', 'LOCAL', None, None)])
                    self.assertEqual((await conn.exec_driver_sql("SELECT usuario_id FROM vinculos")).scalar_one(), 1)
                    await conn.exec_driver_sql("UPDATE usuarios SET usuario_ad = 'pessoa@empresa.local', ad_object_guid = 'guid-exemplo' WHERE id = 1")
                    for coluna, valor in (("usuario_ad", "PESSOA@EMPRESA.LOCAL"), ("ad_object_guid", "guid-exemplo")):
                        with self.assertRaises(IntegrityError):
                            async with conn.begin_nested():
                                await conn.execute(text(f"UPDATE usuarios SET {coluna} = :valor WHERE id = 2"), {"valor": valor})
                finally:
                    await transacao.rollback()
        finally:
            await engine.dispose()

    async def test_migracao_de_etiquetas_preserva_fila_e_separa_tipos_sem_reimprimir(self):
        engine = create_async_engine(os.environ["CNUTRI_TEST_POSTGRES_URL"])
        schema = "teste_etiquetas_" + uuid4().hex
        try:
            async with engine.connect() as conn:
                transacao = await conn.begin()
                try:
                    await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                    await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    await conn.exec_driver_sql("CREATE TABLE trabalhos_impressao (id INTEGER PRIMARY KEY, pedido_id INTEGER, estado VARCHAR(20), dados BYTEA)")
                    await conn.exec_driver_sql("CREATE UNIQUE INDEX uq_impressao_ativa ON trabalhos_impressao (pedido_id) WHERE estado IN ('PENDENTE', 'PROCESSANDO')")
                    await conn.exec_driver_sql("INSERT INTO trabalhos_impressao VALUES (1, 10, 'PENDENTE', decode('010203', 'hex'))")
                    await conn.run_sync(migrar_etiquetas)
                    await conn.run_sync(migrar_etiquetas)
                    antigo = (await conn.exec_driver_sql("SELECT id, pedido_id, estado, dados, tipo_documento, configuracao FROM trabalhos_impressao")).one()
                    self.assertEqual(tuple(antigo), (1, 10, "PENDENTE", b"\x01\x02\x03", "FILIPETA", None))
                    await conn.exec_driver_sql("INSERT INTO trabalhos_impressao (id, pedido_id, estado, tipo_documento) VALUES (2, 10, 'PENDENTE', 'ETIQUETA')")
                    with self.assertRaises(IntegrityError):
                        async with conn.begin_nested():
                            await conn.exec_driver_sql("INSERT INTO trabalhos_impressao (id, pedido_id, estado, tipo_documento) VALUES (3, 10, 'PENDENTE', 'ETIQUETA')")
                    self.assertEqual((await conn.exec_driver_sql("SELECT count(*) FROM trabalhos_impressao")).scalar_one(), 2)
                finally:
                    await transacao.rollback()
        finally:
            await engine.dispose()
    async def test_migracao_operacional_preserva_pedidos_e_protege_chave_por_unidade(self):
        engine = create_async_engine(os.environ["CNUTRI_TEST_POSTGRES_URL"])
        schema = "teste_operacao_" + uuid4().hex
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                    await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    await conn.exec_driver_sql("CREATE TABLE pedidos (id INTEGER PRIMARY KEY, filial_id INTEGER NOT NULL, descricao TEXT)")
                    await conn.exec_driver_sql("INSERT INTO pedidos VALUES (1, 1, 'Pedido histórico com maçã'), (2, 1, 'Outro pedido')")
                    await conn.run_sync(migrar_operacao)
                    await conn.run_sync(migrar_operacao)
                    antigos = (await conn.exec_driver_sql("SELECT id, filial_id, descricao, chave_envio, hash_envio FROM pedidos ORDER BY id")).all()
                    self.assertEqual([tuple(r) for r in antigos], [(1, 1, 'Pedido histórico com maçã', None, None), (2, 1, 'Outro pedido', None, None)])
                    chave = str(uuid4())
                    await conn.execute(text("INSERT INTO pedidos (id, filial_id, chave_envio) VALUES (3, 1, :chave), (4, 2, :chave)"), {"chave": chave})
                    with self.assertRaises(IntegrityError):
                        async with conn.begin_nested():
                            await conn.execute(text("INSERT INTO pedidos (id, filial_id, chave_envio) VALUES (5, 1, :chave)"), {"chave": chave})
                    await conn.run_sync(migrar_operacao)
                    self.assertEqual((await conn.exec_driver_sql("SELECT count(*) FROM pedidos")).scalar_one(), 4)
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    async def test_migracao_preserva_contas_vinculos_e_senhas_e_e_idempotente(self):
        engine = create_async_engine(os.environ["CNUTRI_TEST_POSTGRES_URL"])
        schema = "teste_login_" + uuid4().hex
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                    await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                    await conn.exec_driver_sql("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, email VARCHAR(120) UNIQUE NOT NULL, senha_hash TEXT NOT NULL)")
                    await conn.exec_driver_sql("CREATE TABLE vinculos (usuario_id INTEGER REFERENCES usuarios(id))")
                    await conn.exec_driver_sql("CREATE TABLE entregas_pedidos (pedido_id INTEGER PRIMARY KEY, copeira_nome TEXT)")
                    await conn.exec_driver_sql("INSERT INTO entregas_pedidos VALUES (1, 'Copeira histórica')")
                    emails = ["JOAO@exemplo.local", "joao@outro.local", "joão@teste.local", "x@teste.local", "_@teste.local", "a" * 70 + "@exemplo.local", "a" * 70 + "@outro.local"]
                    for n, email in enumerate(emails, 1):
                        await conn.execute(text("INSERT INTO usuarios VALUES (:id, :email, :hash)"), {"id": n, "email": email, "hash": f"hash-preservado-{n}"})
                    await conn.exec_driver_sql("INSERT INTO vinculos VALUES (1)")
                    await conn.run_sync(migrar_login_usuarios)
                    await conn.run_sync(migrar_seguranca)
                    await conn.run_sync(migrar_seguranca)
                    self.assertFalse((await conn.execute(text("SELECT bool_or(troca_senha_obrigatoria) FROM usuarios"))).scalar_one())
                    antiga = (await conn.execute(text("SELECT copeira_nome, registrado_por_usuario_id FROM entregas_pedidos"))).one()
                    self.assertEqual(tuple(antiga), ("Copeira histórica", None))
                    registros = (await conn.execute(text("SELECT id, email, senha_hash, nome_usuario FROM usuarios ORDER BY id"))).all()
                    self.assertEqual([r.email for r in registros], emails)
                    self.assertEqual([r.senha_hash for r in registros], [f"hash-preservado-{n}" for n in range(1, 8)])
                    nomes = [r.nome_usuario for r in registros]
                    self.assertEqual(nomes[:4], ["joao", "joao_2", "joao_3", "usuario4"])
                    self.assertEqual(len(set(nomes)), len(nomes))
                    self.assertTrue(all(re.fullmatch(PADRAO_USUARIO, nome) for nome in nomes))
                    self.assertEqual((await conn.execute(text("SELECT usuario_id FROM vinculos"))).scalar_one(), 1)
                    await conn.exec_driver_sql("UPDATE usuarios SET nome_usuario = 'escolhido_pela_ti' WHERE id = 1")
                    await conn.run_sync(migrar_login_usuarios)
                    self.assertEqual((await conn.execute(text("SELECT nome_usuario FROM usuarios ORDER BY id"))).scalars().all(), ["escolhido_pela_ti", *nomes[1:]])
                    colunas = await conn.run_sync(lambda c: {r["name"]: r for r in inspect(c).get_columns("usuarios")})
                    self.assertFalse(colunas["nome_usuario"]["nullable"])
                    self.assertTrue(colunas["email"]["nullable"])
                    # Novas contas dispensam e-mail, e a unicidade também vale no banco.
                    await conn.exec_driver_sql("INSERT INTO usuarios (id, senha_hash, nome_usuario) VALUES (8, 'hash', 'novo.usuario'), (9, 'hash', 'outro.usuario')")
                    with self.assertRaises(IntegrityError):
                        async with conn.begin_nested():
                            await conn.exec_driver_sql("INSERT INTO usuarios (id, senha_hash, nome_usuario) VALUES (10, 'hash', 'NOVO.USUARIO')")
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()
