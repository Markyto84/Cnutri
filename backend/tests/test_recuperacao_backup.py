"""Recuperação real de dados fictícios em PostgreSQL, com remoção dos bancos criados."""
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from PIL import Image, ImageDraw
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.gestao import ESQUEMA_PADRAO_ENFERMAGEM
from app.core.database import Base
from app.models.models import Dieta, EntregaPedido, Filial, FormularioConfig, Pedido, Perfil, RecebimentoEntrega, TrabalhoImpressao, Usuario
from app.services.monitoramento import EstadoMonitoramento, obter_monitoramento
from app.services.recuperacao_backup import ComandosPostgres, normalizar_indice, recuperar_e_conferir, resumir_tabelas, validar_alvo


class DestinoRecuperacaoTest(unittest.TestCase):
    def test_cast_equivalente_de_array_nao_oculta_alteracao_de_predicado_ou_unicidade(self):
        a = "CREATE UNIQUE INDEX x ON t (pedido_id,tipo) WHERE ((estado)::text = ANY ((ARRAY['PENDENTE'::character varying, 'PROCESSANDO'::character varying])::text[]))"
        b = "CREATE UNIQUE INDEX x ON t (pedido_id,tipo) WHERE ((estado)::text = ANY (ARRAY[('PENDENTE'::character varying)::text, ('PROCESSANDO'::character varying)::text]))"
        self.assertEqual(normalizar_indice(a), normalizar_indice(b))
        self.assertNotEqual(normalizar_indice(a), normalizar_indice(b.replace("PROCESSANDO", "ENVIADO")))
        self.assertNotEqual(normalizar_indice(a), normalizar_indice(b.replace("UNIQUE ", "")))

    def test_destino_nao_pode_ser_banco_real_nome_arbitrario_ou_prefixo_incompleto(self):
        for nome in ("dietas", "postgres", "cnutri_restore_dietas", "cnutri_restore_1234", 'x"; DROP DATABASE dietas;'):
            with self.assertRaises(ValueError):
                validar_alvo(nome, "dietas")
        correto = "cnutri_restore_" + uuid4().hex
        validar_alvo(correto, "dietas")
        with self.assertRaises(ValueError):
            validar_alvo(correto, correto)


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL") and os.environ.get("CNUTRI_TEST_RECUPERACAO_CONTAINER"),
    "Requer PostgreSQL e contêiner de teste explicitamente indicados")
class RecuperacaoPostgresTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.container = os.environ["CNUTRI_TEST_RECUPERACAO_CONTAINER"]
        base = make_url(os.environ["CNUTRI_TEST_POSTGRES_URL"])
        self.origem = "cnutri_source_test_" + uuid4().hex
        self.url = base.set(database=self.origem)
        self.comandos = ComandosPostgres(self.container, base.username)
        await self.comandos.executar("createdb", ["--template=template0", self.origem])
        self.engine = create_async_engine(self.url)
        self.pasta = TemporaryDirectory(prefix="cnutri-recuperacao-")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with sessoes() as db:
            filial = Filial(nome="Unidade fictícia", codigo_slug="ficticia")
            copeira = Usuario(nome="Copeira fictícia", nome_usuario="copeira", senha_hash="HASH-FICTICIO", perfil=Perfil(nome="COPEIRA"), filiais=[filial])
            dieta = Dieta(filial=filial, nome="GERAL")
            db.add_all([filial, copeira, dieta]); await db.flush()
            self.filial = filial.id
            db.add(FormularioConfig(filial_id=filial.id, tipo_publico="ENFERMAGEM", esquema_json=deepcopy(ESQUEMA_PADRAO_ENFERMAGEM)))
            p = Pedido(filial_id=filial.id, tipo_solicitacao="PACIENTE", solicitante_identificacao="FICTICIO", solicitante_nome="Solicitante fictício",
                nome_paciente="Paciente fictício", dieta=dieta, status="ENTREGUE", dados_dinamicos={})
            db.add(p); await db.flush()
            db.add(TrabalhoImpressao(pedido_id=p.id, tipo_documento="FILIPETA", estado="ENVIADO", dados=b"documento-ficticio", tentativas=1))
            db.add(EntregaPedido(pedido_id=p.id, copeira_id=copeira.id, copeira_nome=copeira.nome, registrado_por_usuario_id=copeira.id))
            await db.flush()
            imagem = Image.new("RGB", (80, 40), "white")
            ImageDraw.Draw(imagem).line([(5, 25), (30, 5), (70, 30)], fill="black", width=2)
            png = BytesIO(); imagem.save(png, format="PNG")
            db.add(RecebimentoEntrega(pedido_id=p.id, recebedor_nome="Recebedor fictício", assinatura_png=png.getvalue()))
            await db.commit()
        async with self.engine.connect() as conn:
            self.antes = await resumir_tabelas(conn)

    async def asyncTearDown(self):
        await self.engine.dispose()
        assert re.fullmatch(r"cnutri_source_test_[0-9a-f]{32}", self.origem)
        await self.comandos.executar("dropdb", [self.origem])
        self.pasta.cleanup()

    async def recuperar(self):
        return await recuperar_e_conferir(self.url, self.container, Path(self.pasta.name))

    async def conferir_origem_e_limpeza(self):
        async with self.engine.connect() as conn:
            self.assertEqual(await resumir_tabelas(conn), self.antes)
            pendentes = (await conn.execute(text("SELECT datname FROM pg_database WHERE datname LIKE 'cnutri_restore_%'"))).all()
            self.assertEqual(pendentes, [])

    async def test_restaura_todos_dados_estruturas_sequencias_formularios_e_assinaturas(self):
        r = await self.recuperar()
        self.assertEqual(r["estado"], "VALIDADO", {k: r.get(k) for k in ("etapa", "erro_tipo")})
        self.assertEqual(r["tabelas"], self.antes)
        self.assertEqual(r["assinaturas_verificadas"], 1)
        self.assertEqual(r["formularios_verificados"], 1)
        self.assertEqual(r["pedidos_verificados"], 1)
        self.assertGreater(r["sequencias_verificadas"], 0)
        self.assertTrue(r["temporario_removido"])
        await self.conferir_origem_e_limpeza()
        async with self.engine.connect() as conn:
            from sqlalchemy.ext.asyncio import AsyncSession
            async with AsyncSession(bind=conn) as db:
                monitor = await obter_monitoramento(db, EstadoMonitoramento(), Path(self.pasta.name) / "nao-existe.json")
                self.assertEqual(monitor["banco"]["estado"], "CONECTADO")
                self.assertGreater(monitor["banco"]["tamanho_bytes"], 0)
                self.assertNotIn("Paciente fictício", str(monitor))

    async def test_falha_na_restauracao_remove_temporario_e_preserva_origem(self):
        original = ComandosPostgres.executar
        async def falhar(instancia, programa, argumentos=(), entrada=None, saida=None):
            if programa == "pg_restore":
                raise RuntimeError("Falha simulada")
            return await original(instancia, programa, argumentos, entrada, saida)
        with patch.object(ComandosPostgres, "executar", falhar):
            r = await self.recuperar()
        self.assertEqual(r["estado"], "FALHOU")
        self.assertEqual(r["etapa"], "restauracao")
        self.assertTrue(r["temporario_removido"])
        await self.conferir_origem_e_limpeza()

    async def test_detecta_registro_divergente_sem_expor_conteudo(self):
        original = ComandosPostgres.executar
        teste = self
        async def adulterar(instancia, programa, argumentos=(), entrada=None, saida=None):
            r = await original(instancia, programa, argumentos, entrada, saida)
            if programa == "pg_restore":
                alvo = argumentos[argumentos.index("-d") + 1]
                validar_alvo(alvo, teste.origem)
                engine = create_async_engine(teste.url.set(database=alvo))
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text("UPDATE pedidos SET nome_paciente='CONTEUDO-NAO-EXPOR'"))
                finally:
                    await engine.dispose()
            return r
        with patch.object(ComandosPostgres, "executar", adulterar):
            r = await self.recuperar()
        self.assertEqual(r["estado"], "FALHOU")
        self.assertNotIn("CONTEUDO-NAO-EXPOR", str(r))
        self.assertTrue(r["temporario_removido"])
        await self.conferir_origem_e_limpeza()

    async def test_snapshot_permite_nova_solicitacao_durante_backup_sem_falsa_divergencia(self):
        original = ComandosPostgres.executar
        teste = self
        async def escrever_apos_dump(instancia, programa, argumentos=(), entrada=None, saida=None):
            r = await original(instancia, programa, argumentos, entrada, saida)
            if programa == "pg_dump":
                async with teste.engine.begin() as conn:
                    await conn.execute(text("""INSERT INTO pedidos (filial_id,tipo_solicitacao,solicitante_identificacao,
                        solicitante_nome,status,dados_dinamicos) VALUES (:filial,'PACIENTE','FICTICIO','Solicitante fictício','PENDENTE','{}')"""), {"filial": teste.filial})
            return r
        with patch.object(ComandosPostgres, "executar", escrever_apos_dump):
            r = await self.recuperar()
        self.assertEqual(r["estado"], "VALIDADO", {k: r.get(k) for k in ("etapa", "erro_tipo")})
        self.assertEqual(r["tabelas"], self.antes)
        self.assertEqual(r["pedidos_verificados"], 1)
        async with self.engine.connect() as conn:
            self.assertEqual(await conn.scalar(text("SELECT count(*) FROM pedidos")), 2)
