"""Regressões dos itens 1–3: credenciais, autorização e formulário vigente, em banco isolado."""
from copy import deepcopy
import asyncio
from datetime import timedelta
import json
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.politica_senha import validar_senha
from app.core.security import hash_senha, verificar_senha
from app.main import app, ws_cozinha
from app.core.ws import gerenciador_ws
from app.models.models import Dieta, EntregaPedido, Filial, FormularioConfig, HistoricoPedido, LimiteLogin, Pedido, Perfil, SessaoUsuario, Usuario

SENHA = "TesteSeguro@123"
NOVA = "Nova@123"
HASH = hash_senha(SENHA)
ESQUEMAS = json.loads((Path(__file__).resolve().parents[2] / "configuracoes/formularios-unidade-havai.json").read_text(encoding="utf-8"))["formularios"]


class SegurancaValidacaoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a, b = Filial(nome="Hospital Fictício A", codigo_slug="teste-a"), Filial(nome="Hospital Fictício B", codigo_slug="teste-b")
            perfis = {nome: Perfil(nome=nome) for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA")}
            db.add_all([a, b, *perfis.values()])
            await db.flush()
            self.a, self.b = a.id, b.id
            self.ids = {}
            for nome, perfil, unidades, obrigatoria in (("admin", "ADMIN_TI", [], False), ("gestor", "NUTRICIONISTA", [a], False),
                ("cozinha", "COZINHA", [a], False), ("ana", "COPEIRA", [a], False), ("bia", "COPEIRA", [a], True),
                ("outro", "COZINHA", [b], False)):
                u = Usuario(nome=nome.title(), nome_usuario=nome, senha_hash=HASH, perfil=perfis[perfil], filiais=unidades, troca_senha_obrigatoria=obrigatoria)
                db.add(u)
                await db.flush()
                self.ids[nome] = u.id
            for tipo, esquema in ESQUEMAS.items():
                db.add(FormularioConfig(filial_id=a.id, tipo_publico=tipo, esquema_json=deepcopy(esquema)))
            dietas = [Dieta(filial_id=a.id, nome="PASTOSA"), Dieta(filial_id=a.id, nome="ANTIGA", ativa=False), Dieta(filial_id=b.id, nome="OUTRA")]
            db.add_all(dietas)
            pedido = Pedido(filial_id=a.id, tipo_solicitacao="MEDICO", solicitante_identificacao="CRM TESTE", solicitante_nome="Pessoa Fictícia", status="PRONTO")
            db.add(pedido)
            await db.commit()
            self.dieta, self.inativa, self.estrangeira = [d.id for d in dietas]
            self.pedido = pedido.id
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.base = f"/api/operacao/unidades/{self.a}/pedidos/{self.pedido}"

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def entrar(self, nome="admin", senha=SENHA):
        r = await self.client.post("/api/auth/login", data={"username": nome, "password": senha})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def comprovante(self):
        return {"copeira_id": self.ids["ana"], "recebedor_nome": "Recebedor Fictício", "assinatura": {
            "tracos": [[{"x": 0.1, "y": 0.7}, {"x": 0.3, "y": 0.2}, {"x": 0.5, "y": 0.6}]]}}

    def medico(self):
        return {"tipo_solicitacao": "MEDICO", "solicitante_identificacao": "CRM TESTE", "solicitante_nome": "Médica Fictícia",
            "observacoes_alergias": "Sem restrições", "dados_dinamicos": {"equipe": "Médica", "horario_entrega": "12:30",
                "refeicao": ESQUEMAS["MEDICO"]["campos"][2]["opcoes"][0], "suco": "COM SUCO", "sobremesa": "SOBREMESA DO DIA", "local_entrega": "TÉRREO - CONFORTO MÉDICO"}}

    def paciente(self):
        return {"tipo_solicitacao": "PACIENTE", "solicitante_identificacao": "COREN TESTE", "solicitante_nome": "Enfermeira Fictícia",
            "prescricao": {"referencia": "Prontuário fictício", "data_hora": "2026-10-20T09:00:00-03:00", "prescritor_nome": "Prescritora Fictícia", "prescritor_registro": "CRN TESTE"},
            "leito": "10", "prontuario": "FICTÍCIO", "nome_paciente": "Paciente Fictício", "dieta_id": self.dieta,
            "observacoes_alergias": "Sem restrições", "dados_dinamicos": {"andar": "TÉRREO - OBSERVAÇÃO", "internado_mais_6h": "Não",
                "matricula": "FICTÍCIA", "data_nascimento": "1970-01-01", "sexo": "FEMININO", "refeicao": "ALMOÇO", "para": "Paciente",
                "cardapio": "SOPA CREME DE LEGUMES", "liquido_espessado": "NÉCTAR"}}

    async def test_anonimo_le_dashboard_mas_nao_muda_cancela_reimprime_ou_entrega(self):
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.a}/pedidos")).status_code, 200)
        with patch("app.services.fila_impressao.enviar_filipeta") as impressora:
            for status in ("EM_PREPARO", "PRONTO", "CANCELADO"):
                self.assertEqual((await self.client.patch(self.base + "/status", json={"status": status})).status_code, 401)
            self.assertEqual((await self.client.post(self.base + "/reimprimir")).status_code, 401)
            self.assertEqual((await self.client.post(self.base + "/entregar", json=self.comprovante())).status_code, 401)
            impressora.assert_not_called()
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, self.pedido)).status, "PRONTO")
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido)), 0)

    async def test_papel_unidade_e_identidade_da_copeira_sao_impostos_pelo_servidor(self):
        ana, outra, cozinha = await self.entrar("ana"), await self.entrar("outro"), await self.entrar("cozinha")
        self.assertEqual((await self.client.patch(self.base + "/status", headers=ana, json={"status": "CANCELADO"})).status_code, 403)
        self.assertEqual((await self.client.post(self.base + "/reimprimir", headers=ana)).status_code, 403)
        for sufixo in ("/status", "/reimprimir"):
            r = await (self.client.patch(self.base + sufixo, headers=outra, json={"status": "CANCELADO"}) if sufixo == "/status" else self.client.post(self.base + sufixo, headers=outra))
            self.assertEqual(r.status_code, 403)
        self.assertEqual((await self.client.post(self.base + "/entregar", headers=cozinha, json=self.comprovante())).status_code, 403)
        self.assertEqual((await self.client.post(self.base + "/entregar", headers=ana, json={**self.comprovante(), "copeira_id": self.ids["bia"]})).status_code, 403)
        r = await self.client.post(self.base + "/entregar", headers=ana, json=self.comprovante())
        self.assertEqual(r.status_code, 201, r.text)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(EntregaPedido, self.pedido)).registrado_por_usuario_id, self.ids["ana"])

    async def test_gestao_registra_por_copeira_online_e_relatorio_identifica_ambas(self):
        await self.entrar("ana")
        gestor = await self.entrar("gestor")
        r = await self.client.post(self.base + "/entregar", headers=gestor, json=self.comprovante())
        self.assertEqual(r.status_code, 201, r.text)
        async with self.sessoes() as db:
            entrega = await db.get(EntregaPedido, self.pedido)
            self.assertEqual(entrega.copeira_id, self.ids["ana"])
            self.assertEqual(entrega.registrado_por_usuario_id, self.ids["gestor"])
            self.assertEqual((await db.scalar(select(HistoricoPedido))).alterado_por_usuario_id, self.ids["gestor"])
        r = await self.client.get(f"/api/relatorios/entregas?filial_id={self.a}", headers=gestor)
        self.assertEqual(r.json()["itens"][0]["registrado_por_nome"], "Gestor")
        self.assertEqual(r.json()["itens"][0]["copeira_nome"], "Ana")

    async def test_primeiro_acesso_da_copeira_exige_nova_senha_antes_de_entrar_no_plantao(self):
        token = await self.entrar("bia")
        me = await self.client.get("/api/auth/me", headers=token)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertTrue(me.json()["troca_senha_obrigatoria"])
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.a}/copeiras")).json(), [])
        self.assertEqual((await self.client.post("/api/auth/presenca", headers=token, json={"filial_id": self.a})).status_code, 403)
        for senha in ("curta", "á" * 37, " " * 12):
            self.assertEqual((await self.client.post("/api/auth/senha", headers=token, json={"senha_atual": SENHA, "nova_senha": senha})).status_code, 422)
        r = await self.client.post("/api/auth/senha", headers=token, json={"senha_atual": SENHA, "nova_senha": NOVA})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["troca_senha_obrigatoria"])
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)
        nova = {"Authorization": "Bearer " + r.json()["access_token"]}
        self.assertEqual((await self.client.post("/api/auth/presenca", headers=nova, json={"filial_id": self.a})).status_code, 200)
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.a}/copeiras", headers=nova)).json()[0]["id"], self.ids["bia"])

    async def test_logout_troca_e_reset_revogam_tokens_anteriores_de_todos_os_perfis(self):
        admin = await self.entrar()
        await self.client.post("/api/auth/logout", headers=admin)
        self.assertEqual((await self.client.get("/api/admin/usuarios", headers=admin)).status_code, 401)
        gestor = await self.entrar("gestor")
        r = await self.client.post("/api/auth/senha", headers=gestor, json={"senha_atual": SENHA, "nova_senha": NOVA})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.get("/api/auth/me", headers=gestor)).status_code, 401)
        token = {"Authorization": "Bearer " + r.json()["access_token"]}
        admin = await self.entrar()
        r = await self.client.patch(f"/api/admin/usuarios/{self.ids['gestor']}", headers=admin, json={"nome": "Gestor", "nome_usuario": "gestor",
            "perfil": "NUTRICIONISTA", "filial_ids": [self.a], "senha": "TempNova@12"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)
        novo = await self.entrar("gestor", "TempNova@12")
        self.assertEqual((await self.client.get(f"/api/pedidos?filial_id={self.a}", headers=novo)).status_code, 403)

    async def test_logout_troca_e_reset_fecham_canais_privados_sem_fechar_o_dashboard(self):
        publico, outro = AsyncMock(), AsyncMock()
        await gerenciador_ws.conectar_publico(self.a, publico)
        await gerenciador_ws.conectar(self.a, outro, self.ids["ana"])
        canais = [publico, outro]
        try:
            admin = await self.entrar()
            for acao, nome in (("logout", "gestor"), ("troca", "cozinha"), ("reset", "gestor")):
                with self.subTest(acao=acao):
                    token = await self.entrar(nome)
                    canal = AsyncMock()
                    canais.append(canal)
                    await gerenciador_ws.conectar(self.a, canal, self.ids[nome])
                    if acao == "logout":
                        r = await self.client.post("/api/auth/logout", headers=token)
                    elif acao == "troca":
                        r = await self.client.post("/api/auth/senha", headers=token, json={"senha_atual": SENHA, "nova_senha": NOVA})
                    else:
                        r = await self.client.patch(f"/api/admin/usuarios/{self.ids[nome]}", headers=admin, json={"nome": "Gestor", "nome_usuario": nome,
                            "perfil": "NUTRICIONISTA", "filial_ids": [self.a], "senha": "TempNova@12"})
                    self.assertEqual(r.status_code, 200, r.text)
                    canal.close.assert_awaited_once_with(code=1008)
                    self.assertNotIn(canal, gerenciador_ws.usuarios)
                    self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)
                    publico.close.assert_not_awaited()
                    outro.close.assert_not_awaited()
        finally:
            for canal in canais:
                gerenciador_ws.desconectar(self.a, canal)

    async def test_websocket_ja_aberto_detecta_sessao_expirada_sem_nova_mensagem(self):
        token = (await self.entrar("gestor"))["Authorization"].removeprefix("Bearer ")
        aceito = asyncio.Event()
        canal = AsyncMock()
        canal.scope = {"subprotocols": ["cnutri", token]}
        async def aceitar(**_kwargs):
            aceito.set()
        async def aguardar():
            await asyncio.Event().wait()
        canal.accept.side_effect = aceitar
        canal.receive_text.side_effect = aguardar
        tarefa = None
        try:
            with patch("app.main.SessionLocal", self.sessoes), patch("app.main.INTERVALO_VALIDACAO_WS", 0.02):
                tarefa = asyncio.create_task(ws_cozinha(canal, self.a))
                await asyncio.wait_for(aceito.wait(), 2)
                async with self.sessoes() as db:
                    await db.execute(update(SessaoUsuario).where(SessaoUsuario.usuario_id == self.ids["gestor"]).values(expira_em=agora_utc() - timedelta(seconds=1)))
                    await db.commit()
                await asyncio.wait_for(tarefa, 2)
            canal.close.assert_awaited_once_with(code=1008)
            self.assertNotIn(canal, gerenciador_ws.usuarios)
        finally:
            if tarefa and not tarefa.done():
                tarefa.cancel()
                await asyncio.gather(tarefa, return_exceptions=True)
            gerenciador_ws.desconectar(self.a, canal)

    async def test_regra_de_senha_vale_no_cadastro_reset_e_troca_sem_alterar_senhas_legadas(self):
        admin, gestor = await self.entrar(), await self.entrar("gestor")
        credencial = {"nome": "Pessoa Teste", "nome_usuario": "nova.pessoa", "perfil": "COZINHA", "filial_ids": [self.a]}
        for senha in ("Ab1!xyz", "Ab1!abcdefghi", "abcdef1!", "Abcdefg1", "ABCDEF!@", "Teste12 "):
            with self.subTest(senha=senha):
                self.assertEqual((await self.client.post("/api/admin/usuarios", headers=admin, json={**credencial, "senha": senha})).status_code, 422)
                self.assertEqual((await self.client.patch(f"/api/admin/usuarios/{self.ids['gestor']}", headers=admin,
                    json={**credencial, "nome_usuario": "gestor", "perfil": "NUTRICIONISTA", "senha": senha})).status_code, 422)
                self.assertEqual((await self.client.post("/api/auth/senha", headers=gestor,
                    json={"senha_atual": SENHA, "nova_senha": senha})).status_code, 422)
        await self.entrar("gestor")  # senha existente com mais de 12 caracteres continua válida.
        self.assertEqual((await self.client.get("/api/auth/me", headers=gestor)).status_code, 200)
        async with self.sessoes() as db:
            self.assertIsNone(await db.scalar(select(Usuario).where(Usuario.nome_usuario == "nova.pessoa")))

    async def test_cria_com_oito_caracteres_e_troca_para_doze_com_revogacao(self):
        admin = await self.entrar()
        r = await self.client.post("/api/admin/usuarios", headers=admin, json={"nome": "Pessoa Teste", "nome_usuario": "nova.pessoa",
            "perfil": "COZINHA", "filial_ids": [self.a], "senha": "TESTE1!?"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["troca_senha_obrigatoria"])
        anterior = await self.entrar("nova.pessoa", "TESTE1!?")
        troca = await self.client.post("/api/auth/senha", headers=anterior, json={"senha_atual": "TESTE1!?", "nova_senha": "NovaSenha12!"})
        self.assertEqual(troca.status_code, 200, troca.text)
        self.assertFalse(troca.json()["troca_senha_obrigatoria"])
        self.assertEqual((await self.client.get("/api/auth/me", headers=anterior)).status_code, 401)
        await self.entrar("nova.pessoa", "NovaSenha12!")

    async def test_cinco_falhas_limitam_login_persistido_sem_expor_senha_nos_logs(self):
        with self.assertLogs("cnutri.seguranca", level="WARNING") as logs:
            for _ in range(5):
                self.assertEqual((await self.client.post("/api/auth/login", data={"username": "admin", "password": "Errada@2026"})).status_code, 401)
        self.assertNotIn("Errada@2026", "".join(logs.output))
        r = await self.client.post("/api/auth/login", data={"username": "ADMIN", "password": SENHA})
        self.assertEqual(r.status_code, 429)
        self.assertGreater(int(r.headers["Retry-After"]), 0)
        await self.entrar("gestor")
        async with self.sessoes() as db:
            await db.execute(update(LimiteLogin).values(janela_inicio=agora_utc() - timedelta(minutes=16)))
            await db.commit()
        await self.entrar()

    async def test_token_antigo_sem_sessao_e_segredo_publico_sao_recusados(self):
        token = jwt.encode({"sub": str(self.ids["admin"]), "exp": agora_utc() + timedelta(hours=1)}, settings.JWT_SECRET)
        self.assertEqual((await self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token})).status_code, 401)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, JWT_SECRET="troque-este-segredo-em-producao")
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, APP_ENV="production", JWT_SECRET="x" * 64, DATABASE_URL="postgresql+asyncpg://dietas:dietas@db:5432/dietas")

    async def test_rotacao_inicial_preserva_senha_personalizada_e_entrega_somente_em_arquivo(self):
        from atualizar_seguranca import atualizar
        async with self.sessoes() as db:
            (await db.get(Usuario, self.ids["admin"])).senha_hash = hash_senha("Trocar@123")
            await db.commit()
        saida = StringIO()
        with TemporaryDirectory() as pasta, redirect_stdout(saida), patch("atualizar_seguranca.SessionLocal", self.sessoes), \
            patch("atualizar_seguranca.engine", SimpleNamespace(begin=self.engine.begin, dispose=AsyncMock())):
            arquivo = Path(pasta) / "temporarias.txt"
            await atualizar(arquivo)
            conteudo = arquivo.read_text(encoding="utf-8")
            senha = conteudo.split("Senha temporária: ")[1].splitlines()[0]
            self.assertEqual(len(senha), 12)
            self.assertEqual(validar_senha(senha), senha)
            self.assertNotIn(senha, saida.getvalue())
            async with self.sessoes() as db:
                admin = await db.get(Usuario, self.ids["admin"])
                self.assertTrue(verificar_senha(senha, admin.senha_hash))
                self.assertTrue(admin.troca_senha_obrigatoria)
                self.assertTrue(verificar_senha(SENHA, (await db.get(Usuario, self.ids["ana"])).senha_hash))
            await atualizar(Path(pasta) / "segunda.txt")
            self.assertFalse((Path(pasta) / "segunda.txt").exists())

    async def test_pedidos_validos_de_ambos_formularios_preservam_acento_e_campos(self):
        for dados in (self.medico(), self.paciente()):
            r = await self.client.post("/api/public/teste-a/pedidos", json=dados)
            self.assertEqual(r.status_code, 201, r.text)
            self.assertNotIn("dados_dinamicos", r.json())
            async with self.sessoes() as db:
                self.assertEqual((await db.get(Pedido, r.json()["id"])).dados_dinamicos, dados["dados_dinamicos"])

    async def test_campos_obrigatorios_opcoes_tipos_tamanhos_e_datas_invalidos_nao_gravam_nem_imprimem(self):
        alteracoes = [lambda p: p.update(solicitante_identificacao="  "), lambda p: p.update(solicitante_nome="  "),
            lambda p: p.update(observacoes_alergias=" "), lambda p: p.update(leito="x" * 31),
            lambda p: p.update(dieta_id=self.inativa), lambda p: p.update(dieta_id=self.estrangeira),
            lambda p: p.update(dieta_id=True), lambda p: p.update(dieta_id=1.5),
            lambda p: p["dados_dinamicos"].update(andar="Inexistente"), lambda p: p["dados_dinamicos"].pop("matricula"),
            lambda p: p["dados_dinamicos"].update(matricula=["valor"]), lambda p: p["dados_dinamicos"].update(matricula="x" * 1001),
            lambda p: p["dados_dinamicos"].update(data_nascimento="2026-02-30"), lambda p: p["dados_dinamicos"].update(data_nascimento="2099-01-01"),
            lambda p: p["dados_dinamicos"].update(cardapio="Cardápio de outro grupo"), lambda p: p["dados_dinamicos"].update(campo_desconhecido="valor"),
            lambda p: p["dados_dinamicos"].update(nome_paciente="duplicado"), lambda p: p.update(refeicao="fora do JSON"),
            lambda p: p.update(observacoes_alergias="x" * 5001)]
        with patch("app.services.fila_impressao.enviar_filipeta") as imprimir:
            for alterar in alteracoes:
                p = self.paciente()
                alterar(p)
                r = await self.client.post("/api/public/teste-a/pedidos", json=p)
                self.assertEqual(r.status_code, 422, r.text)
            imprimir.assert_not_called()
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(Pedido)), 1)

    async def test_formulario_atual_prevalece_apos_edicao_do_gestor(self):
        token = await self.entrar("gestor")
        rota = f"/api/gestao/formularios/{self.a}/MEDICO"
        atual = (await self.client.get(rota, headers=token)).json()
        esquema = deepcopy(atual["esquema_json"])
        esquema["campos"][2]["opcoes"] = ["NOVO CARDÁPIO"]
        r = await self.client.put(rota, headers=token, json={"esquema_json": esquema, "versao": atual["atualizado_em"]})
        self.assertEqual(r.status_code, 200, r.text)
        r = await self.client.post("/api/public/teste-a/pedidos", json=self.medico())
        self.assertEqual(r.status_code, 422)
        self.assertIn("Refeição", r.text)
        atual = (await self.client.get(rota, headers=token)).json()
        esquema["campos"].append(deepcopy(esquema["campos"][0]))
        self.assertEqual((await self.client.put(rota, headers=token, json={"esquema_json": esquema, "versao": atual["atualizado_em"]})).status_code, 422)
        self.assertEqual((await self.client.post("/api/public/teste-b/pedidos", json=self.medico())).status_code, 409)
