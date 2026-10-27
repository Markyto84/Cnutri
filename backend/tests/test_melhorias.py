"""Fluxos operacionais em banco isolado; nenhum envio para impressoras reais."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
import unittest
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.api.gestao import ESQUEMA_PADRAO_ENFERMAGEM
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.core.migracao_melhorias import migrar_melhorias
from app.main import app
from app.models.models import AuditoriaAdministrativa, EventoAssistencial, Filial, FormularioConfig, Pedido, Perfil, TrabalhoImpressao, Usuario


class MelhoriasTest(unittest.IsolatedAsyncioTestCase):
    async def criar_engine(self):
        return create_async_engine("sqlite+aiosqlite:///:memory:")

    async def asyncSetUp(self):
        self.engine = await self.criar_engine()
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(migrar_melhorias)
            await conn.run_sync(migrar_melhorias)
        async with self.sessoes() as db:
            a = Filial(nome="Unidade A", codigo_slug="unidade-a", ip_impressora="192.0.2.10")
            b = Filial(nome="Unidade B", codigo_slug="unidade-b", ip_impressora="192.0.2.20")
            db.add_all([a, b])
            await db.flush()
            self.a, self.b = a.id, b.id
            for perfil in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA"):
                db.add(Usuario(nome="Pessoa fictícia " + perfil, nome_usuario=perfil.lower(),
                    senha_hash="hash-nao-usado-nos-testes-de-autorizacao", perfil=Perfil(nome=perfil), filiais=[a]))
            db.add(FormularioConfig(filial_id=self.a, tipo_publico="ENFERMAGEM", atualizado_em=datetime(2025, 1, 1),
                esquema_json=deepcopy(ESQUEMA_PADRAO_ENFERMAGEM)))
            await db.commit()

        async def banco():
            async with self.sessoes() as db:
                yield db

        async def usuario(request: Request, db=Depends(get_db)):
            nome = request.headers.get("X-Perfil-Teste")
            if not nome:
                raise HTTPException(401, "Teste sem autenticação")
            return await db.scalar(select(Usuario).options(selectinload(Usuario.perfil), selectinload(Usuario.filiais))
                .where(Usuario.nome_usuario == nome.lower()))

        app.dependency_overrides[get_db] = banco
        app.dependency_overrides[get_current_user] = usuario
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.admin = {"X-Perfil-Teste": "ADMIN_TI"}
        self.gestor = {"X-Perfil-Teste": "NUTRICIONISTA"}
        self.cozinha = {"X-Perfil-Teste": "COZINHA"}
        self.copeira = {"X-Perfil-Teste": "COPEIRA"}

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()
        if hasattr(self, "admin_engine"):
            async with self.admin_engine.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
            await self.admin_engine.dispose()

    async def test_cancelamento_exige_motivo_e_preserva_autor_solicitante_e_horario(self):
        for legado in (False, True):
            pedido = await self.pedido(estado="PENDENTE")
            url = f"/api/pedidos/{pedido}/status" if legado else f"/api/operacao/unidades/{self.a}/pedidos/{pedido}/status"
            for motivo in (None, "", "    ", "abcd", "a" * 1001):
                r = await self.client.patch(url, headers=self.cozinha, json={"status": "CANCELADO", "motivo": motivo})
                self.assertEqual(r.status_code, 422, r.text)
            motivo = "  Refeição solicitada em duplicidade.  "
            r = await self.client.patch(url, headers=self.cozinha, json={"status": "CANCELADO", "motivo": motivo})
            self.assertEqual(r.status_code, 200, r.text)
            repetido = await self.client.patch(url, headers=self.admin, json={"status": "CANCELADO", "motivo": "Não sobrescrever o motivo"})
            self.assertEqual(repetido.status_code, 200 if legado else 409)
            async with self.sessoes() as db:
                eventos = (await db.scalars(select(EventoAssistencial).where(EventoAssistencial.pedido_id == pedido))).all()
                self.assertEqual(len(eventos), 1)
                evento = eventos[0]
                self.assertEqual(evento.motivo, motivo.strip())
                self.assertEqual(evento.autor_nome, "Pessoa fictícia COZINHA")
                self.assertIsNotNone(evento.criado_em)
            relatorio = await self.client.get("/api/relatorios/dietas-periodo", headers=self.admin,
                params={"inicio": "2020-01-01T00:00:00Z", "fim": "2100-01-01T00:00:00Z", "status": "CANCELADO"})
            self.assertEqual(relatorio.status_code, 200, relatorio.text)
            item = next(i for i in relatorio.json()["itens"] if i["pedido_id"] == pedido)
            self.assertEqual(item["solicitante_nome"], "Solicitante fictício")
            self.assertEqual(item["solicitante_identificacao"], "FICTICIO")
            self.assertEqual(item["cancelado_por_nome"], evento.autor_nome)
            self.assertEqual(item["cancelado_por_usuario_id"], evento.autor_usuario_id)
            self.assertEqual(item["motivo_cancelamento"], motivo.strip())
            self.assertTrue(item["cancelado_em"])
            self.assertEqual(relatorio.json()["totais"]["cancelados"], 2 if legado else 1)

    async def test_nutricao_mantem_textos_e_listas_mas_so_ti_altera_estrutura(self):
        url = f"/api/gestao/formularios/{self.a}/ENFERMAGEM"
        atual = (await self.client.get(url, headers=self.gestor)).json()
        for chave, valor in (("rotulo", "Outro nome"), ("obrigatorio", False)):
            esquema = deepcopy(atual["esquema_json"])
            esquema["campos"][0][chave] = valor
            self.assertEqual((await self.client.put(url, headers=self.gestor, json={"esquema_json": esquema})).status_code, 403)
        esquema = deepcopy(atual["esquema_json"])
        esquema["campos"].append({"id": "campo_novo", "tipo": "texto", "rotulo": "Novo campo"})
        self.assertEqual((await self.client.put(url, headers=self.gestor, json={"esquema_json": esquema})).status_code, 403)
        self.assertEqual((await self.client.post(url + "/resetar", headers=self.gestor)).status_code, 403)
        esquema["campos"].extend([
            {"id": "refeicao", "tipo": "selecao", "rotulo": "Refeição", "opcoes": ["Almoço"]},
            {"id": "liquido_espessado", "tipo": "selecao", "rotulo": "Líquido espessado", "opcoes": ["NÉCTAR", "MEL"]},
            {"id": "cardapio", "tipo": "cardapio", "rotulo": "Cardápio", "grupos": []},
        ])
        self.assertEqual((await self.client.put(url, headers=self.admin, json={"esquema_json": esquema})).status_code, 200)
        esquema = (await self.client.get(url, headers=self.gestor)).json()["esquema_json"]
        esquema["cabecalho"] = "Novo aviso da Nutrição"
        lista = next(c for c in esquema["campos"] if c["tipo"] in ("selecao", "radio") and c["id"] != "liquido_espessado")
        lista["opcoes"] = ["Nova opção"]
        next(c for c in esquema["campos"] if c["id"] == "tipo_liquido_espessado")["opcoes"] = ["PUDIM"]
        cardapio = next((c for c in esquema["campos"] if c["tipo"] == "cardapio"), None)
        if cardapio:
            cardapio["grupos"] = [{"nome": "Geral", "dietas": ["GERAL"], "opcoes": ["Refeição nova"]}]
        r = await self.client.put(url, headers=self.gestor, json={"esquema_json": esquema})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["esquema_json"], esquema)

    async def pedido(self, filial=None, estado="PRONTO"):
        async with self.sessoes() as db:
            p = Pedido(filial_id=filial or self.a, tipo_solicitacao="PACIENTE", solicitante_identificacao="FICTICIO",
                solicitante_nome="Solicitante fictício", nome_paciente="Não deve aparecer na central", status=estado,
                dados_dinamicos={"matricula": "DADO-NAO-EXPOSTO"})
            db.add(p)
            await db.commit()
            return p.id

    async def trabalho(self, pedido, estado="FALHA", tipo="FILIPETA", antigo=False):
        async with self.sessoes() as db:
            job = TrabalhoImpressao(pedido_id=pedido, estado=estado, tipo_documento=tipo,
                configuracao={"segredo": "NAO-EXPOSTO"}, dados=b"DOCUMENTO-NAO-EXPOSTO",
                criado_em=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=20 if antigo else 0))
            db.add(job)
            await db.commit()
            return job.id

    async def historico(self, headers=None, **params):
        r = await self.client.get("/api/gestao/auditoria", headers=headers or self.admin, params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    async def test_alertas_padrao_editaveis_por_unidade_e_desativacao(self):
        url = f"/api/gestao/alertas/{self.a}"
        publico = f"/api/operacao/unidades/{self.a}/alertas"
        self.assertEqual((await self.client.get(publico)).json(), {"preparo_minutos": 30, "entrega_minutos": 30})
        dados = {"preparo_minutos": 45, "entrega_minutos": None}
        r = await self.client.put(url, headers=self.gestor, json=dados)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.get(publico)).json(), dados)
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.b}/alertas")).json()["preparo_minutos"], 30)
        h = await self.historico()
        self.assertEqual(h["total"], 1)
        self.assertEqual(h["itens"][0]["antes"], {"preparo_minutos": 30, "entrega_minutos": 30})
        self.assertEqual(h["itens"][0]["depois"], dados)
        await self.client.put(url, headers=self.gestor, json=dados)
        self.assertEqual((await self.historico())["total"], 1, "Salvar sem mudança não deve inventar uma alteração")

    async def test_configuracao_rejeita_sem_permissao_e_prazos_invalidos(self):
        url = f"/api/gestao/alertas/{self.a}"
        self.assertEqual((await self.client.put(url, json={})).status_code, 401)
        self.assertEqual((await self.client.put(url, headers=self.cozinha, json={})).status_code, 403)
        self.assertEqual((await self.client.put(f"/api/gestao/alertas/{self.b}", headers=self.gestor, json={})).status_code, 403)
        for valor in (0, -1, 1441, True, "30", 2.5):
            self.assertEqual((await self.client.put(url, headers=self.admin, json={"preparo_minutos": valor})).status_code, 422)
        self.assertEqual((await self.historico())["total"], 0)

    async def test_central_filtros_paginacao_isolamento_e_projecao_sem_documentos(self):
        a, b = await self.pedido(), await self.pedido(self.b)
        await self.trabalho(a)
        await self.trabalho(a, estado="ENVIADO", tipo="ETIQUETA")
        await self.trabalho(a, antigo=True)
        await self.trabalho(b)
        self.assertEqual((await self.client.get("/api/impressoes")).status_code, 401)
        self.assertEqual((await self.client.get("/api/impressoes", headers=self.copeira)).status_code, 403)
        r = await self.client.get("/api/impressoes", headers=self.gestor, params={"tamanho": 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total"], 2)
        self.assertEqual(len(r.json()["itens"]), 1)
        self.assertNotIn("Não deve aparecer", r.text)
        self.assertNotIn("NAO-EXPOSTO", r.text)
        self.assertNotIn("configuracao", r.text)
        pagina2 = (await self.client.get("/api/impressoes", headers=self.gestor, params={"tamanho": 1, "pagina": 2})).json()
        self.assertNotEqual(r.json()["itens"][0]["id"], pagina2["itens"][0]["id"])
        filtrado = await self.client.get("/api/impressoes", headers=self.admin, params={"tipo": "ETIQUETA", "estado": "ENVIADO", "pedido_id": a, "filial_id": self.a})
        self.assertEqual(filtrado.json()["total"], 1)
        self.assertEqual((await self.client.get("/api/impressoes", headers=self.gestor, params={"filial_id": self.b})).status_code, 403)
        self.assertEqual((await self.client.get("/api/impressoes", headers=self.admin)).json()["total"], 3)
        self.assertIn("no-store", r.headers["cache-control"])

    async def test_central_reenvia_falha_na_fila_e_rejeita_repeticao_de_trabalho_antigo(self):
        p = await self.pedido()
        job = await self.trabalho(p)
        r = await self.client.post(f"/api/impressoes/{job}/reenviar", headers=self.cozinha, json={})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertTrue(r.json()["enfileirado"])
        self.assertNotEqual(r.json()["impressao"]["id"], job)
        self.assertEqual((await self.client.post(f"/api/impressoes/{job}/reenviar", headers=self.admin, json={})).status_code, 409)
        async with self.sessoes() as db:
            linhas = (await db.scalars(select(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == p).order_by(TrabalhoImpressao.id))).all()
            self.assertEqual([j.estado for j in linhas], ["FALHA", "PENDENTE"])
            self.assertIsNotNone(linhas[-1].solicitado_por_usuario_id)

    async def test_envio_incerto_exige_conferencia_e_etiqueta_somente_pronto(self):
        p = await self.pedido(estado="PENDENTE")
        job = await self.trabalho(p, estado="INCERTO")
        url = f"/api/impressoes/{job}/reenviar"
        self.assertEqual((await self.client.post(url, headers=self.admin, json={})).status_code, 409)
        self.assertEqual((await self.client.post(url, headers=self.admin, json={"confirmar_risco_duplicidade": True})).status_code, 202)
        etiqueta = await self.trabalho(p, tipo="ETIQUETA")
        self.assertEqual((await self.client.post(f"/api/impressoes/{etiqueta}/reenviar", headers=self.admin, json={})).status_code, 409)
        consulta = (await self.client.get("/api/impressoes", headers=self.admin)).json()
        self.assertTrue(all(not i["pode_reenviar"] for i in consulta["itens"]))

    async def test_historico_dieta_antes_depois_e_permissoes(self):
        r = await self.client.post(f"/api/gestao/dietas?filial_id={self.a}", headers=self.gestor, json={"nome": "Geral fictícia"})
        self.assertEqual(r.status_code, 201, r.text)
        dieta = r.json()["id"]
        await self.client.patch(f"/api/gestao/dietas/{dieta}", headers=self.gestor, json={"nome": "Nome revisado", "severa": True})
        await self.client.delete(f"/api/gestao/dietas/{dieta}", headers=self.gestor)
        h = await self.historico(entidade="DIETA")
        self.assertEqual(h["total"], 3)
        alteracao = h["itens"][1]
        self.assertEqual(alteracao["antes"], {"nome": "Geral fictícia", "severa": False})
        self.assertEqual(alteracao["depois"], {"nome": "Nome revisado", "severa": True})
        self.assertIn("NUTRICIONISTA", alteracao["autor_nome"])
        self.assertEqual((await self.client.get("/api/gestao/auditoria", headers=self.cozinha)).status_code, 403)
        self.assertEqual((await self.client.get("/api/gestao/auditoria", headers=self.gestor, params={"filial_id": self.b})).status_code, 403)

    async def test_historico_formulario_cardapio_e_publicacao_antiga_sem_alteracao(self):
        url = f"/api/gestao/formularios/{self.a}/ENFERMAGEM"
        atual = (await self.client.get(url, headers=self.gestor)).json()
        esquema = deepcopy(atual["esquema_json"])
        esquema["titulo"] = "Novo título fictício"
        r = await self.client.put(url, headers=self.gestor, json={"esquema_json": esquema, "versao": atual["atualizado_em"]})
        self.assertEqual(r.status_code, 200, r.text)
        h = await self.historico(entidade="FORMULARIO")
        self.assertEqual(h["total"], 1)
        self.assertEqual(h["itens"][0]["antes"]["esquema_json"], atual["esquema_json"])
        self.assertEqual(h["itens"][0]["depois"]["esquema_json"], esquema)
        r = await self.client.put(url, headers=self.gestor, json={"esquema_json": atual["esquema_json"], "versao": atual["atualizado_em"]})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual((await self.historico(entidade="FORMULARIO"))["total"], 1)

    async def test_credencial_e_impressoras_auditadas_sem_senhas_ou_hash(self):
        dados = {"nome": "Credencial fictícia", "nome_usuario": "nova", "senha": "Audit#123", "perfil": "COZINHA", "filial_ids": [self.a]}
        r = await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)
        self.assertEqual(r.status_code, 201, r.text)
        novo = r.json()["id"]
        r = await self.client.patch(f"/api/admin/usuarios/{novo}", headers=self.admin, json={**dados, "senha": "Outra#123", "perfil": "NUTRICIONISTA"})
        self.assertEqual(r.status_code, 200, r.text)
        await self.client.patch(f"/api/admin/filiais/{self.a}/impressora", headers=self.admin, json={"ip_impressora": "192.0.2.30"})
        await self.client.patch(f"/api/admin/filiais/{self.a}/etiquetas", headers=self.admin, json={"modelo": "Modelo fictício", "ip": "192.0.2.40"})
        h = await self.historico()
        self.assertEqual(h["total"], 4)
        texto = json.dumps(h)
        for segredo in ("Audit#123", "Outra#123", "senha_hash", "hash-nao-usado", "access_token"):
            self.assertNotIn(segredo, texto)
        self.assertEqual(len([i for i in h["itens"] if i["entidade"] == "CREDENCIAL"]), 2)
        self.assertEqual((await self.client.get("/api/gestao/auditoria", headers=self.gestor, params={"entidade": "CREDENCIAL"})).status_code, 403)

    async def test_historico_somente_ti_mesmo_com_filtros_e_gestor_continua_auditado(self):
        r = await self.client.put(f"/api/gestao/alertas/{self.a}", headers=self.gestor,
            json={"preparo_minutos": 45, "entrega_minutos": 60})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.get("/api/gestao/auditoria")).status_code, 401)
        for headers in (self.gestor, self.cozinha, self.copeira):
            for params in ({}, {"filial_id": self.a}, {"entidade": "ALERTAS"}, {"entidade": "CREDENCIAL"}):
                r = await self.client.get("/api/gestao/auditoria", headers=headers, params=params)
                self.assertEqual(r.status_code, 403, r.text)
                self.assertNotIn("itens", r.json())
        h = await self.historico(entidade="ALERTAS")
        self.assertEqual(h["total"], 1)
        self.assertIn("NUTRICIONISTA", h["itens"][0]["autor_nome"])
        self.assertEqual(h["itens"][0]["depois"], {"preparo_minutos": 45, "entrega_minutos": 60})

    async def test_nova_unidade_registra_formularios_e_dietas_copiados(self):
        await self.client.post(f"/api/gestao/dietas?filial_id={self.a}", headers=self.gestor, json={"nome": "Geral de origem"})
        r = await self.client.post("/api/admin/filiais", headers=self.admin,
            json={"nome": "Nova unidade", "codigo_slug": "nova-unidade", "origem_filial_id": self.a})
        self.assertEqual(r.status_code, 201, r.text)
        h = await self.historico(filial_id=r.json()["id"])
        self.assertEqual(h["total"], 4)
        self.assertEqual(sorted(i["entidade"] for i in h["itens"]), ["DIETA", "FORMULARIO", "FORMULARIO", "UNIDADE"])
        self.assertTrue(all(i["antes"] is None and i["acao"] == "CRIAR" for i in h["itens"]))

    async def test_falha_de_transacao_nao_deixa_historico_e_periodo_invalido_rejeitado(self):
        r = await self.client.patch(f"/api/admin/filiais/{self.a}", headers=self.admin, json={"nome": "Não persistir", "codigo_slug": "unidade-b"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual((await self.historico())["total"], 0)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Filial, self.a)).nome, "Unidade A")
        for caminho in ("/api/gestao/auditoria", "/api/impressoes"):
            r = await self.client.get(caminho, headers=self.admin, params={"inicio": "2026-10-26", "fim": "2026-10-25"})
            self.assertEqual(r.status_code, 422)
            self.assertEqual((await self.client.get(caminho, headers=self.admin, params={"pagina": 10**30})).status_code, 422)
            self.assertEqual((await self.client.get(caminho, headers=self.admin, params={"inicio": "9999-12-31", "fim": "9999-12-31"})).status_code, 422)


@unittest.skipUnless(os.environ.get("CNUTRI_TEST_POSTGRES_URL"), "Requer PostgreSQL de teste")
class MelhoriasPostgresTest(MelhoriasTest):
    async def criar_engine(self):
        url = os.environ["CNUTRI_TEST_POSTGRES_URL"]
        self.schema = "teste_melhorias_" + uuid4().hex
        self.admin_engine = create_async_engine(url)
        async with self.admin_engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        return create_async_engine(url, connect_args={"server_settings": {"search_path": self.schema}})

    async def test_duas_retentativas_simultaneas_criam_so_um_novo_trabalho(self):
        pedido = await self.pedido()
        job = await self.trabalho(pedido)
        url = f"/api/impressoes/{job}/reenviar"
        respostas = await asyncio.gather(*[self.client.post(url, headers=self.cozinha, json={}) for _ in range(2)])
        self.assertEqual(sorted(r.status_code for r in respostas), [202, 409])
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao).where(TrabalhoImpressao.pedido_id == pedido)), 2)

    async def test_duas_publicacoes_com_mesma_versao_preservam_historico_real(self):
        url = f"/api/gestao/formularios/{self.a}/ENFERMAGEM"
        original = (await self.client.get(url, headers=self.gestor)).json()
        async def publicar(titulo):
            return await self.client.put(url, headers=self.gestor, json={"versao": original["atualizado_em"],
                "esquema_json": {**original["esquema_json"], "titulo": titulo}})
        respostas = await asyncio.gather(publicar("Título A"), publicar("Título B"))
        self.assertEqual(sorted(r.status_code for r in respostas), [200, 409])
        h = await self.historico(entidade="FORMULARIO")
        self.assertEqual(h["total"], 1)
        self.assertEqual(h["itens"][0]["antes"]["esquema_json"], original["esquema_json"])
        atual = (await self.client.get(url, headers=self.gestor)).json()
        self.assertEqual(h["itens"][0]["depois"]["esquema_json"], atual["esquema_json"])
