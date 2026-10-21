"""Fluxo público, presença por login e entrega única; banco isolado em memória."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.security import hash_senha
from app.core.ws import gerenciador_ws
from app.main import app, ws_cozinha, ws_operacao
from app.models.models import EntregaPedido, Filial, HistoricoPedido, Pedido, Perfil, RecebimentoEntrega, SessaoCopeira, Usuario

SENHA = "TesteSeguro@123"
HASH = hash_senha(SENHA)


class SocketTeste:
    def __init__(self):
        self.aceito = False
        self.fechado = None
        self.mensagens = []

    async def accept(self, **kwargs):
        self.aceito = True

    async def close(self, code=1000):
        self.fechado = code

    async def receive_text(self):
        raise RuntimeError("Fim do teste")

    async def send_json(self, mensagem):
        self.mensagens.append(mensagem)


class EntregasTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a, b = Filial(nome="Unidade A", codigo_slug="unidade-a"), Filial(nome="Unidade B", codigo_slug="unidade-b")
            perfil = Perfil(nome="COPEIRA")
            admin = Perfil(nome="ADMIN_TI")
            gestor = Perfil(nome="NUTRICIONISTA")
            db.add_all([a, b, perfil, admin, gestor])
            await db.flush()
            self.a, self.b = a.id, b.id
            ana = Usuario(nome="Ana Teste", nome_usuario="ana", email="ana@teste.local", senha_hash=HASH, perfil=perfil, filiais=[a, b])
            bia = Usuario(nome="Bia Teste", nome_usuario="bia", email="bia@teste.local", senha_hash=HASH, perfil=perfil, filiais=[a])
            db.add_all([ana, bia, Usuario(nome="Admin Teste", nome_usuario="admin", email="admin@teste.local", senha_hash=HASH, perfil=admin, filiais=[])])
            db.add(Usuario(nome="Gestor B", nome_usuario="gestor", email="gestor@teste.local", senha_hash=HASH, perfil=gestor, filiais=[b]))
            await db.flush()
            self.ana, self.bia = ana.id, bia.id
            self.pedidos = {}
            for etapa in ("PENDENTE", "EM_PREPARO", "PRONTO", "CANCELADO"):
                pedido = Pedido(filial_id=a.id, tipo_solicitacao="PACIENTE", solicitante_identificacao="COREN PRIVADO",
                    solicitante_nome="Profissional Teste", nome_paciente="Paciente Fictício", prontuario="PRONTUARIO PRIVADO",
                    status=etapa, dados_dinamicos={"refeicao": "ALMOÇO", "andar": "TÉRREO", "data_nascimento": "1958-04-23", "matricula": "MATRICULA PRIVADA", "sexo": "FEMININO"})
                db.add(pedido)
                await db.flush()
                self.pedidos[etapa] = pedido.id
            await db.commit()

        async def banco_teste():
            async with self.sessoes() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.base = f"/api/operacao/unidades/{self.a}"
        self.operador = await self.entrar("admin")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def entrar(self, nome_usuario="ana"):
        resposta = await self.client.post("/api/auth/login", data={"username": nome_usuario, "password": SENHA})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return {"Authorization": "Bearer " + resposta.json()["access_token"]}

    def comprovante(self):
        return {"copeira_id": self.ana, "recebedor_nome": "Recebedor Fictício",
            "assinatura": {"tracos": [[{"x": 0.1, "y": 0.7}, {"x": 0.3, "y": 0.2}, {"x": 0.5, "y": 0.6}]]}}

    async def test_dashboard_abre_sem_login_e_publica_apenas_dados_operacionais(self):
        unidades = await self.client.get("/api/operacao/unidades")
        self.assertEqual(unidades.status_code, 200)
        self.assertNotIn("ip_impressora", unidades.text)
        resposta = await self.client.get(self.base + "/pedidos")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual({p["status"] for p in resposta.json()}, {"PENDENTE", "EM_PREPARO", "PRONTO"})
        for privado in ("prontuario", "solicitante_identificacao", "matricula", "data_nascimento", "sexo"):
            self.assertNotIn(privado, resposta.text)
        self.assertIsInstance(resposta.json()[0]["idade"], int)
        self.assertEqual((await self.client.get("/api/admin/usuarios")).status_code, 401)
        self.assertEqual((await self.client.get(f"/api/pedidos?filial_id={self.a}")).status_code, 401)

    async def test_login_aparece_logout_remove_e_invalida_sessao(self):
        self.assertEqual((await self.client.get(self.base + "/copeiras")).json(), [])
        token = await self.entrar()
        self.assertEqual((await self.client.get(self.base + "/copeiras")).json(), [{"id": self.ana, "nome": "Ana Teste"}])
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.b}/copeiras")).json(), [])
        self.assertEqual((await self.client.post("/api/auth/logout", headers=token)).status_code, 200)
        self.assertEqual((await self.client.get(self.base + "/copeiras")).json(), [])
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)

    async def test_presenca_segue_unidade_e_expira_sem_apagar_credencial(self):
        token = await self.entrar()
        resposta = await self.client.post("/api/auth/presenca", headers=token, json={"filial_id": self.b})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual((await self.client.get(self.base + "/copeiras")).json(), [])
        self.assertEqual(len((await self.client.get(f"/api/operacao/unidades/{self.b}/copeiras")).json()), 1)
        async with self.sessoes() as db:
            sessao = (await db.execute(select(SessaoCopeira))).scalar_one()
            sessao.presenca_ate = agora_utc() - timedelta(seconds=1)
            await db.commit()
        self.assertEqual((await self.client.get(f"/api/operacao/unidades/{self.b}/copeiras")).json(), [])
        self.assertEqual((await self.client.post("/api/auth/presenca", headers=token, json={"filial_id": self.a})).status_code, 200)
        self.assertEqual(len((await self.client.get(self.base + "/copeiras")).json()), 1)
        bia = await self.entrar("bia")
        self.assertEqual((await self.client.post("/api/auth/presenca", headers=bia, json={"filial_id": self.b})).status_code, 403)

    async def test_duas_abas_ou_sessoes_nao_duplicam_nome(self):
        primeira, segunda = await self.entrar(), await self.entrar()
        self.assertEqual(len((await self.client.get(self.base + "/copeiras")).json()), 1)
        await self.client.post("/api/auth/logout", headers=primeira)
        self.assertEqual(len((await self.client.get(self.base + "/copeiras")).json()), 1)
        await self.client.post("/api/auth/logout", headers=segunda)
        self.assertEqual((await self.client.get(self.base + "/copeiras")).json(), [])

    async def test_entrega_registra_copeira_horario_historico_e_nao_duplica(self):
        await self.entrar()
        pedido_id = self.pedidos["PRONTO"]
        rota = self.base + f"/pedidos/{pedido_id}/entregar"
        resposta = await self.client.post(rota, headers=self.operador, json=self.comprovante())
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual(resposta.json()["copeira_nome"], "Ana Teste")
        self.assertTrue(resposta.json()["entregue_em"].endswith("+00:00"))
        self.assertNotIn(pedido_id, [p["id"] for p in (await self.client.get(self.base + "/pedidos")).json()])
        self.assertEqual((await self.client.post(rota, headers=self.operador, json=self.comprovante())).status_code, 409)
        self.assertEqual((await self.client.patch(self.base + f"/pedidos/{pedido_id}/status", headers=self.operador, json={"status": "PRONTO"})).status_code, 409)
        admin = await self.entrar("admin")
        self.assertEqual((await self.client.patch(f"/api/pedidos/{pedido_id}/status", headers=admin, json={"status": "PRONTO"})).status_code, 409)
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(EntregaPedido)), 1)
            entrega = await db.get(EntregaPedido, pedido_id)
            self.assertEqual(entrega.copeira_id, self.ana)
            historico = (await db.execute(select(HistoricoPedido).where(HistoricoPedido.pedido_id == pedido_id))).scalar_one()
            self.assertEqual(historico.status_novo, "ENTREGUE")

    async def test_painel_interno_nao_sobrescreve_entrega_concorrente(self):
        pedido_id = self.pedidos["PRONTO"]
        admin = await self.entrar("admin")

        async def entrega_durante_leitura(filial_id, usuario, db):
            # Simula a entrega confirmada depois que o painel leu o status antigo.
            await db.execute(update(Pedido).where(Pedido.id == pedido_id)
                .values(status="ENTREGUE").execution_options(synchronize_session=False))
            await db.commit()

        with patch("app.api.pedidos.verificar_acesso_filial", entrega_durante_leitura):
            resposta = await self.client.patch(f"/api/pedidos/{pedido_id}/status", headers=admin, json={"status": "CANCELADO"})
        self.assertEqual(resposta.status_code, 409, resposta.text)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, pedido_id)).status, "ENTREGUE")

    async def test_consumo_medico_mantem_refeicao_apos_entrega(self):
        pedido_id = self.pedidos["PRONTO"]
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, pedido_id)
            pedido.tipo_solicitacao = "MEDICO"
            await db.commit()
        admin = await self.entrar("admin")
        rota = f"/api/relatorios/consumo-medico?filial_id={self.a}"
        antes = (await self.client.get(rota, headers=admin)).json()
        await self.entrar()
        resposta = await self.client.post(self.base + f"/pedidos/{pedido_id}/entregar", headers=self.operador, json=self.comprovante())
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual((await self.client.get(rota, headers=admin)).json(), antes)
        self.assertEqual(sum(item["total"] for item in antes), 1)

    async def test_consumo_medico_classifica_limites_de_turno_em_brasilia(self):
        casos = [(datetime(2026, 10, 21, 8, 59), "Noite"), (datetime(2026, 10, 21, 9), "Manhã"),
            (datetime(2026, 10, 21, 14, 59), "Manhã"), (datetime(2026, 10, 21, 15), "Tarde"),
            (datetime(2026, 10, 21, 20, 59), "Tarde"), (datetime(2026, 10, 21, 21), "Noite"),
            (datetime(2026, 10, 21, 2, 59), "Noite"), (datetime(2026, 10, 21, 3), "Noite")]
        async with self.sessoes() as db:
            for n, (data, _) in enumerate(casos):
                db.add(Pedido(filial_id=self.a, tipo_solicitacao="MEDICO", solicitante_identificacao="TESTE",
                    solicitante_nome=f"Caso {n}", criado_em=data, status="PRONTO"))
            await db.commit()
        resposta = await self.client.get(f"/api/relatorios/consumo-medico?filial_id={self.a}", headers=self.operador)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual({r["solicitante"]: r["turno"] for r in resposta.json()}, {f"Caso {n}": turno for n, (_, turno) in enumerate(casos)})

    async def test_nao_entrega_sem_copeira_online_ou_sem_refeicao_pronta(self):
        rota = self.base + f"/pedidos/{self.pedidos['PRONTO']}/entregar"
        self.assertEqual((await self.client.post(rota, headers=self.operador, json=self.comprovante())).status_code, 409)
        token = await self.entrar()
        for etapa in ("PENDENTE", "EM_PREPARO", "CANCELADO"):
            resultado = await self.client.post(self.base + f"/pedidos/{self.pedidos[etapa]}/entregar", headers=self.operador, json=self.comprovante())
            self.assertEqual(resultado.status_code, 409)
        self.assertEqual((await self.client.post(rota, headers=self.operador, json={})).status_code, 422)
        await self.client.post("/api/auth/logout", headers=token)
        self.assertEqual((await self.client.post(rota, headers=self.operador, json=self.comprovante())).status_code, 409)

    async def test_sem_assinatura_valida_nao_conclui_nem_grava_entrega(self):
        await self.entrar()
        rota = self.base + f"/pedidos/{self.pedidos['PRONTO']}/entregar"
        invalidos = [
            {"copeira_id": self.ana},
            {**self.comprovante(), "recebedor_nome": "   "},
            {**self.comprovante(), "assinatura": {"tracos": []}},
            {**self.comprovante(), "assinatura": {"tracos": [[{"x": 0.5, "y": 0.5}, {"x": 0.5, "y": 0.5}]]}},
            {**self.comprovante(), "assinatura": {"tracos": [[{"x": -1, "y": 0}, {"x": 1, "y": 1}]]}},
            {**self.comprovante(), "assinatura": {"tracos": [[{"x": 0.2, "y": 0.3}] * 1501]}},
        ]
        for dados in invalidos:
            resposta = await self.client.post(rota, headers=self.operador, json=dados)
            self.assertEqual(resposta.status_code, 422, resposta.text)
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, self.pedidos['PRONTO'])).status, "PRONTO")
            for modelo in (EntregaPedido, RecebimentoEntrega, HistoricoPedido):
                self.assertEqual(await db.scalar(select(func.count()).select_from(modelo)), 0)

    async def test_assinatura_e_horario_servidor_aparecem_so_no_relatorio_autorizado(self):
        copeira = await self.entrar()
        pedido_id = self.pedidos["PRONTO"]
        antes = datetime.now(timezone.utc) - timedelta(seconds=1)
        resposta = await self.client.post(self.base + f"/pedidos/{pedido_id}/entregar", headers=self.operador,
            json={**self.comprovante(), "entregue_em": "2000-01-01T00:00:00Z"})
        self.assertEqual(resposta.status_code, 201, resposta.text)
        entregue = datetime.fromisoformat(resposta.json()["entregue_em"])
        self.assertGreaterEqual(entregue, antes)
        self.assertLessEqual(entregue, datetime.now(timezone.utc))
        self.assertTrue(resposta.json()["assinatura_registrada"])
        relatorio = f"/api/relatorios/entregas?filial_id={self.a}"
        imagem = f"/api/relatorios/entregas/{pedido_id}/assinatura?filial_id={self.a}"
        for rota in (relatorio, imagem):
            self.assertEqual((await self.client.get(rota)).status_code, 401)
            self.assertEqual((await self.client.get(rota, headers=copeira)).status_code, 403)
        gestor_b = await self.entrar("gestor")
        for rota in (relatorio, imagem):
            self.assertEqual((await self.client.get(rota, headers=gestor_b)).status_code, 403)
        admin = await self.entrar("admin")
        resultado = (await self.client.get(relatorio, headers=admin)).json()
        self.assertEqual(resultado["total"], 1)
        item = resultado["itens"][0]
        self.assertEqual(item["recebedor_nome"], "Recebedor Fictício")
        self.assertEqual(item["copeira_nome"], "Ana Teste")
        self.assertEqual(item["entregue_em"], resposta.json()["entregue_em"])
        self.assertTrue(item["assinatura_disponivel"])
        arquivo = await self.client.get(imagem, headers=admin)
        self.assertEqual(arquivo.headers["content-type"], "image/png")
        self.assertIn("no-store", arquivo.headers["cache-control"])
        png = Image.open(BytesIO(arquivo.content))
        self.assertEqual(png.size, (1000, 500))
        self.assertEqual(png.getextrema(), (20, 255))
        self.assertEqual((await self.client.get(imagem.replace(f"filial_id={self.a}", f"filial_id={self.b}"), headers=admin)).status_code, 404)
        async with self.sessoes() as db:
            recibo = await db.get(RecebimentoEntrega, pedido_id)
            self.assertEqual(recibo.assinatura_png, arquivo.content)

    async def test_falha_ao_salvar_assinatura_reverte_entrega_inteira(self):
        await self.entrar()
        pedido_id = self.pedidos["PRONTO"]
        with patch("app.api.operacao.gerar_assinatura_png", side_effect=RuntimeError("Falha simulada")):
            with self.assertRaisesRegex(RuntimeError, "Falha simulada"):
                await self.client.post(self.base + f"/pedidos/{pedido_id}/entregar", headers=self.operador, json=self.comprovante())
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Pedido, pedido_id)).status, "PRONTO")
            for modelo in (EntregaPedido, RecebimentoEntrega, HistoricoPedido):
                self.assertEqual(await db.scalar(select(func.count()).select_from(modelo)), 0)

    async def test_relatorio_filtra_data_brasilia_e_preserva_entrega_antiga_sem_assinatura(self):
        async with self.sessoes() as db:
            for etapa, horario in (("PRONTO", datetime(2026, 10, 21, 2, 59, 59)), ("PENDENTE", datetime(2026, 10, 21, 3))):
                pedido_id = self.pedidos[etapa]
                (await db.get(Pedido, pedido_id)).status = "ENTREGUE"
                db.add(EntregaPedido(pedido_id=pedido_id, copeira_id=self.ana, copeira_nome="Ana Teste", entregue_em=horario))
            await db.commit()
        admin = await self.entrar("admin")
        rota = f"/api/relatorios/entregas?filial_id={self.a}"
        for dia in ("2026-10-20", "2026-10-21"):
            resposta = await self.client.get(rota + f"&data_inicio={dia}&data_fim={dia}", headers=admin)
            self.assertEqual(resposta.status_code, 200, resposta.text)
            self.assertEqual(resposta.json()["total"], 1)
            self.assertFalse(resposta.json()["itens"][0]["assinatura_disponivel"])
        self.assertEqual((await self.client.get(rota + "&data_inicio=2026-10-21&data_fim=2026-10-20", headers=admin)).status_code, 422)

    async def test_etapas_e_unidades_sao_respeitadas_com_operador_autorizado(self):
        pedido_id = self.pedidos["PENDENTE"]
        rota = self.base + f"/pedidos/{pedido_id}/status"
        self.assertEqual((await self.client.patch(rota, headers=self.operador, json={"status": "PRONTO"})).status_code, 409)
        self.assertEqual((await self.client.patch(rota, headers=self.operador, json={"status": "EM_PREPARO"})).status_code, 200)
        self.assertEqual((await self.client.patch(rota, headers=self.operador, json={"status": "PRONTO"})).status_code, 200)
        self.assertEqual((await self.client.patch(rota, headers=self.operador, json={"status": "ENTREGUE"})).status_code, 422)
        outro = f"/api/operacao/unidades/{self.b}/pedidos/{pedido_id}/status"
        self.assertEqual((await self.client.patch(outro, headers=self.operador, json={"status": "CANCELADO"})).status_code, 404)
        async with self.sessoes() as db:
            filial = await db.get(Filial, self.a)
            filial.ativa = False
            await db.commit()
        for sufixo in ("/pedidos", "/copeiras"):
            self.assertEqual((await self.client.get(self.base + sufixo)).status_code, 404)

    async def test_websocket_publico_tem_dados_filtrados_e_fecha_unidade_inativa(self):
        token = await self.entrar()
        with patch("app.main.SessionLocal", self.sessoes):
            interno = SocketTeste()
            interno.scope = {"subprotocols": ["cnutri", token["Authorization"].removeprefix("Bearer ")]}
            await ws_cozinha(interno, self.a)
            self.assertFalse(interno.aceito)
            self.assertEqual(interno.fechado, 1008)
            socket = SocketTeste()
            await ws_operacao(socket, self.a)
            self.assertTrue(socket.aceito)
            async with self.sessoes() as db:
                filial = await db.get(Filial, self.a)
                filial.ativa = False
                await db.commit()
            bloqueado = SocketTeste()
            await ws_operacao(bloqueado, self.a)
            self.assertEqual(bloqueado.fechado, 1008)
        socket = SocketTeste()
        await gerenciador_ws.conectar_publico(self.a, socket)
        try:
            await gerenciador_ws.transmitir(self.a, {"evento": "novo_pedido", "pedido": {
                "id": 1, "filial_id": self.a, "tipo_solicitacao": "PACIENTE", "status": "PRONTO",
                "prontuario": "PRIVADO", "dados_dinamicos": {"matricula": "PRIVADO", "refeicao": "JANTAR"},
            }})
            self.assertNotIn("prontuario", socket.mensagens[0]["pedido"])
            self.assertEqual(socket.mensagens[0]["pedido"]["dados_dinamicos"], {"refeicao": "JANTAR"})
        finally:
            gerenciador_ws.desconectar(self.a, socket)


if __name__ == "__main__":
    unittest.main()
