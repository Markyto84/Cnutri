"""Fluxo público, presença por login e entrega única; banco isolado em memória."""
from datetime import timedelta
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.presenca import agora_utc
from app.core.security import hash_senha
from app.core.ws import gerenciador_ws
from app.main import app, ws_cozinha, ws_operacao
from app.models.models import EntregaPedido, Filial, HistoricoPedido, Pedido, Perfil, SessaoCopeira, Usuario

SENHA = "Teste@123"
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
            db.add_all([a, b, perfil, admin])
            await db.flush()
            self.a, self.b = a.id, b.id
            ana = Usuario(nome="Ana Teste", email="ana@teste.local", senha_hash=HASH, perfil=perfil, filiais=[a, b])
            bia = Usuario(nome="Bia Teste", email="bia@teste.local", senha_hash=HASH, perfil=perfil, filiais=[a])
            db.add_all([ana, bia, Usuario(nome="Admin Teste", email="admin@teste.local", senha_hash=HASH, perfil=admin, filiais=[])])
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

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def entrar(self, email="ana@teste.local"):
        resposta = await self.client.post("/api/auth/login", data={"username": email, "password": SENHA})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return {"Authorization": "Bearer " + resposta.json()["access_token"]}

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
        bia = await self.entrar("bia@teste.local")
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
        resposta = await self.client.post(rota, json={"copeira_id": self.ana})
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual(resposta.json()["copeira_nome"], "Ana Teste")
        self.assertTrue(resposta.json()["entregue_em"].endswith("+00:00"))
        self.assertNotIn(pedido_id, [p["id"] for p in (await self.client.get(self.base + "/pedidos")).json()])
        self.assertEqual((await self.client.post(rota, json={"copeira_id": self.ana})).status_code, 409)
        self.assertEqual((await self.client.patch(self.base + f"/pedidos/{pedido_id}/status", json={"status": "PRONTO"})).status_code, 409)
        admin = await self.entrar("admin@teste.local")
        self.assertEqual((await self.client.patch(f"/api/pedidos/{pedido_id}/status", headers=admin, json={"status": "PRONTO"})).status_code, 409)
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(EntregaPedido)), 1)
            entrega = await db.get(EntregaPedido, pedido_id)
            self.assertEqual(entrega.copeira_id, self.ana)
            historico = (await db.execute(select(HistoricoPedido).where(HistoricoPedido.pedido_id == pedido_id))).scalar_one()
            self.assertEqual(historico.status_novo, "ENTREGUE")

    async def test_painel_interno_nao_sobrescreve_entrega_concorrente(self):
        pedido_id = self.pedidos["PRONTO"]
        admin = await self.entrar("admin@teste.local")

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
        admin = await self.entrar("admin@teste.local")
        rota = f"/api/relatorios/consumo-medico?filial_id={self.a}"
        antes = (await self.client.get(rota, headers=admin)).json()
        await self.entrar()
        resposta = await self.client.post(self.base + f"/pedidos/{pedido_id}/entregar", json={"copeira_id": self.ana})
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual((await self.client.get(rota, headers=admin)).json(), antes)
        self.assertEqual(sum(item["total"] for item in antes), 1)

    async def test_nao_entrega_sem_copeira_online_ou_sem_refeicao_pronta(self):
        rota = self.base + f"/pedidos/{self.pedidos['PRONTO']}/entregar"
        self.assertEqual((await self.client.post(rota, json={"copeira_id": self.ana})).status_code, 409)
        token = await self.entrar()
        for etapa in ("PENDENTE", "EM_PREPARO", "CANCELADO"):
            resultado = await self.client.post(self.base + f"/pedidos/{self.pedidos[etapa]}/entregar", json={"copeira_id": self.ana})
            self.assertEqual(resultado.status_code, 409)
        self.assertEqual((await self.client.post(rota, json={})).status_code, 422)
        await self.client.post("/api/auth/logout", headers=token)
        self.assertEqual((await self.client.post(rota, json={"copeira_id": self.ana})).status_code, 409)

    async def test_etapas_e_unidades_sao_respeitadas_sem_login(self):
        pedido_id = self.pedidos["PENDENTE"]
        rota = self.base + f"/pedidos/{pedido_id}/status"
        self.assertEqual((await self.client.patch(rota, json={"status": "PRONTO"})).status_code, 409)
        self.assertEqual((await self.client.patch(rota, json={"status": "EM_PREPARO"})).status_code, 200)
        self.assertEqual((await self.client.patch(rota, json={"status": "PRONTO"})).status_code, 200)
        self.assertEqual((await self.client.patch(rota, json={"status": "ENTREGUE"})).status_code, 422)
        outro = f"/api/operacao/unidades/{self.b}/pedidos/{pedido_id}/status"
        self.assertEqual((await self.client.patch(outro, json={"status": "CANCELADO"})).status_code, 404)
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
