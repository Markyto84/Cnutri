"""Monitoramento autorizado e agregado; não acessa dados operacionais."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import Filial, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.fila_impressao import executar_fila
from app.services.monitoramento import EstadoMonitoramento, SinalFila, ler_recuperacao, sondar_banco


class MonitoramentoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            f = Filial(nome="Fictícia", codigo_slug="ficticia")
            db.add(f)
            for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA"):
                db.add(Usuario(nome=nome, nome_usuario=nome.lower(), senha_hash="hash-ficticio", perfil=Perfil(nome=nome), filiais=[f]))
            await db.commit()
            self.filial_id = f.id

        async def banco():
            async with self.sessoes() as db:
                yield db

        async def pessoa(request: Request, db=Depends(get_db)):
            nome = request.headers.get("X-Perfil-Teste")
            if not nome:
                raise HTTPException(401)
            return await db.scalar(select(Usuario).options(selectinload(Usuario.perfil), selectinload(Usuario.filiais)).where(Usuario.nome_usuario == nome))

        app.dependency_overrides[get_db] = banco
        app.dependency_overrides[get_current_user] = pessoa
        self.estado_anterior = getattr(app.state, "monitoramento", None)
        app.state.monitoramento = EstadoMonitoramento()
        app.state.monitoramento.fila.ativa = True
        app.state.monitoramento.fila.registrar(True)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.admin = {"X-Perfil-Teste": "admin_ti"}

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        if self.estado_anterior is None:
            del app.state.monitoramento
        else:
            app.state.monitoramento = self.estado_anterior
        await self.engine.dispose()

    async def test_monitoramento_exclusivo_ti_e_sonda_publica_minima(self):
        self.assertEqual((await self.client.get("/api/admin/monitoramento")).status_code, 401)
        for perfil in ("nutricionista", "cozinha", "copeira"):
            self.assertEqual((await self.client.get("/api/admin/monitoramento", headers={"X-Perfil-Teste": perfil})).status_code, 403)
        r = await self.client.get("/api/admin/monitoramento", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["banco"]["estado"], "CONECTADO")
        self.assertEqual(r.json()["consumidor"]["estado"], "ATIVA")
        self.assertIn("no-store", r.headers["cache-control"])
        r = await self.client.get("/api/health/ready")
        self.assertEqual(r.json(), {"status": "ok"})
        self.assertEqual((await self.client.get("/api/health")).json(), {"status": "ok"})

    async def test_falha_de_banco_nao_vaza_erro_e_prontidao_503(self):
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("postgresql://senha-secreta@banco/paciente")
        r = await sondar_banco(db)
        self.assertEqual(r, {"estado": "INDISPONIVEL", "latencia_ms": None})
        db.rollback.assert_awaited_once()
        with patch("app.api.monitoramento.sondar_banco", AsyncMock(return_value=r)):
            resposta = await self.client.get("/api/health/ready")
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"status": "indisponivel"})
        self.assertNotIn("senha", resposta.text)

    async def test_fila_ignora_falha_antiga_resolvida_e_pedido_finalizado(self):
        async with self.sessoes() as db:
            async def pedido(status):
                p = Pedido(filial_id=self.filial_id, tipo_solicitacao="PACIENTE", solicitante_identificacao="NAO-EXPOR",
                    solicitante_nome="Solicitante Fictício", nome_paciente="PACIENTE-NAO-EXPOR", status=status, dados_dinamicos={})
                db.add(p); await db.flush(); return p
            a, b, c = await pedido("PRONTO"), await pedido("PRONTO"), await pedido("ENTREGUE")
            for p, estados in ((a, ["FALHA", "ENVIADO"]), (b, ["INCERTO"]), (c, ["FALHA"])):
                for estado in estados:
                    db.add(TrabalhoImpressao(pedido_id=p.id, tipo_documento="FILIPETA", estado=estado, dados=b"DOCUMENTO-NAO-EXPOR"))
                    await db.flush()
            db.add(TrabalhoImpressao(pedido_id=a.id, tipo_documento="ETIQUETA", estado="PENDENTE",
                criado_em=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)))
            await db.commit()
        r = await self.client.get("/api/admin/monitoramento", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        fila = r.json()["fila"]
        self.assertEqual(fila["falhas_atuais"], 0)
        self.assertEqual(fila["incertos_atuais"], 1)
        self.assertEqual(fila["contadores_24h"]["PENDENTE"], 1)
        self.assertIsNotNone(fila["pendente_mais_antigo_em"])
        self.assertNotIn("NAO-EXPOR", r.text)
        self.assertNotIn("nome_paciente", r.text)

    async def test_consumidor_publica_ciclo_sucesso_falha_e_encerramento(self):
        sinal, parar = SinalFila(), asyncio.Event()
        async def processar(_):
            parar.set()
            return False
        with patch("app.services.fila_impressao.recuperar_interrompidos", AsyncMock()), patch("app.services.fila_impressao.processar_um", processar):
            await executar_fila(None, parar, sinal)
        self.assertIsNotNone(sinal.ultimo_sucesso_em)
        self.assertFalse(sinal.ativa)
        self.assertEqual(sinal.resumo()["estado"], "PARADA")
        sinal.ativa = True
        sinal.ultimo_ciclo_em = datetime.now(timezone.utc) - timedelta(minutes=3)
        self.assertEqual(sinal.resumo()["estado"], "ATENCAO")
        sinal.registrar(False)
        self.assertEqual(sinal.falhas_consecutivas, 1)
        self.assertEqual(sinal.resumo()["estado"], "ATENCAO")
        sinal.registrar(True)
        self.assertEqual(sinal.resumo()["estado"], "ATIVA")


class RelatorioRecuperacaoTest(unittest.TestCase):
    def test_relatorio_retorna_somente_resumo_sem_dados_privados(self):
        with TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "resultado.json"
            self.assertEqual(ler_recuperacao(arquivo)["estado"], "SEM_TESTE")
            teste = {"estado": "VALIDADO", "iniciado_em": "2026-10-26T12:00:00Z", "concluido_em": "2026-10-26T12:00:02Z",
                "temporario_removido": True, "tabelas_verificadas": 16, "senha": "NUNCA-EXPOR", "caminho": "CAMINHO-PRIVADO"}
            arquivo.write_text(json.dumps({"versao": 1, "ultimo_teste": teste, "ultima_validacao": teste, "token": "NUNCA-EXPOR"}), encoding="utf-8")
            r = ler_recuperacao(arquivo)
            self.assertEqual(r["estado"], "VALIDADO")
            self.assertNotIn("NUNCA-EXPOR", json.dumps(r))
            self.assertNotIn("CAMINHO-PRIVADO", json.dumps(r))

    def test_arquivo_incompleto_incorreto_ou_validacao_sem_limpeza_nao_indica_sucesso(self):
        with TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "resultado.json"
            for conteudo in ("{", "x" * 65537, json.dumps({"versao": 1, "ultimo_teste": {"estado": "VALIDADO", "iniciado_em": "2026-10-26T12:00:00Z"}})):
                arquivo.write_text(conteudo, encoding="utf-8")
                self.assertEqual(ler_recuperacao(arquivo)["estado"], "INCONSISTENTE")
