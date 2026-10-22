"""Integração administrativa em SQLite isolado; não usa o banco do hospital."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import hash_senha
from app.main import app, ws_cozinha
from app.models.models import Dieta, Filial, FormularioConfig, Perfil, Usuario

SENHA = "Teste@123"
HASH = hash_senha(SENHA)


class SocketTeste:
    def __init__(self, protocolos):
        self.scope = {"subprotocols": protocolos}
        self.aceito = False
        self.fechado = None

    async def accept(self, subprotocol=None):
        self.aceito = subprotocol

    async def close(self, code=1000):
        self.fechado = code

    async def receive_text(self):
        raise RuntimeError("Fim da conexão de teste")


class AdministracaoTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)
        snapshot = Path(__file__).resolve().parents[2] / "configuracoes/formularios-unidade-havai.json"
        self.esquemas = json.loads(snapshot.read_text(encoding="utf-8"))["formularios"]
        async with self.sessoes() as db:
            perfis = {nome: Perfil(nome=nome) for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA")}
            a, b = Filial(nome="Unidade A", codigo_slug="unidade-a"), Filial(nome="Unidade B", codigo_slug="unidade-b")
            db.add_all([*perfis.values(), a, b])
            await db.flush()
            self.a, self.b = a.id, b.id
            for tipo, esquema in self.esquemas.items():
                db.add(FormularioConfig(filial_id=a.id, tipo_publico=tipo, esquema_json=deepcopy(esquema)))
            db.add(Dieta(filial_id=a.id, nome="GERAL", ativa=True, severa=False))
            admin = Usuario(nome="Admin Teste", nome_usuario="admin", email="admin@teste.local", senha_hash=HASH, perfil=perfis["ADMIN_TI"], filiais=[])
            db.add_all([
                admin,
                Usuario(nome="Gestor Teste", nome_usuario="gestor", email="gestor@teste.local", senha_hash=HASH, perfil=perfis["NUTRICIONISTA"], filiais=[a]),
                Usuario(nome="Cozinha Teste", nome_usuario="cozinha", email="cozinha@teste.local", senha_hash=HASH, perfil=perfis["COZINHA"], filiais=[a]),
            ])
            await db.commit()
            self.admin_id = admin.id

        async def banco_teste():
            async with self.sessoes() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
        self.admin = await self.entrar("admin")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def entrar(self, nome_usuario, senha=SENHA):
        resposta = await self.client.post("/api/auth/login", data={"username": nome_usuario, "password": senha})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return {"Authorization": "Bearer " + resposta.json()["access_token"]}

    async def test_admin_lista_usuarios_sem_expor_senhas_e_acessa_todas_unidades(self):
        resposta = await self.client.get("/api/admin/usuarios", headers=self.admin)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual({u["perfil"] for u in resposta.json()}, {"ADMIN_TI", "NUTRICIONISTA", "COZINHA"})
        self.assertTrue(all("senha_hash" not in u and "senha" not in u for u in resposta.json()))
        me = (await self.client.get("/api/auth/me", headers=self.admin)).json()
        self.assertEqual({f["id"] for f in me["filiais"]}, {self.a, self.b})
        self.assertEqual((await self.client.get(f"/api/gestao/dietas?filial_id={self.b}", headers=self.admin)).status_code, 200)

    async def test_nova_unidade_copia_configuracoes_sem_compartilhar_edicoes(self):
        origem = (await self.client.get("/api/public/unidade-a/config")).json()
        resposta = await self.client.post("/api/admin/filiais", headers=self.admin, json={
            "nome": "Unidade C", "codigo_slug": "unidade-c", "origem_filial_id": self.a,
        })
        self.assertEqual(resposta.status_code, 201, resposta.text)
        nova = resposta.json()["id"]
        config = (await self.client.get("/api/public/unidade-c/config")).json()
        self.assertEqual(config["formularios"], origem["formularios"])
        salvo_enfermagem = (await self.client.get(f"/api/gestao/formularios/{nova}/ENFERMAGEM", headers=self.admin)).json()
        self.assertEqual(salvo_enfermagem["esquema_json"], self.esquemas["ENFERMAGEM"])
        self.assertEqual([d["nome"] for d in config["dietas"]], ["GERAL"])
        self.assertIsNone(resposta.json()["ip_impressora"])
        atual = (await self.client.get(f"/api/gestao/formularios/{nova}/MEDICO", headers=self.admin)).json()
        alterado = deepcopy(atual["esquema_json"])
        alterado["titulo"] = "Exclusivo da C"
        salvo = await self.client.put(f"/api/gestao/formularios/{nova}/MEDICO", headers=self.admin, json={
            "esquema_json": alterado, "versao": atual["atualizado_em"],
        })
        self.assertEqual(salvo.status_code, 200, salvo.text)
        original = (await self.client.get("/api/public/unidade-a/config")).json()
        self.assertEqual(original["formularios"], origem["formularios"])
        repetido = await self.client.post("/api/admin/filiais", headers=self.admin, json={"nome": "Outra", "codigo_slug": "unidade-c"})
        self.assertEqual(repetido.status_code, 409)

    async def test_criar_editar_credencial_senha_e_desativar(self):
        dados = {"nome": "Nova Pessoa", "nome_usuario": "PESSOA", "senha": SENHA, "perfil": "NUTRICIONISTA", "filial_ids": [self.b]}
        resposta = await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        usuario = resposta.json()
        self.assertEqual(usuario["nome_usuario"], "pessoa")
        self.assertEqual([f["id"] for f in usuario["filiais"]], [self.b])
        await self.entrar("pessoa")
        dados.update(nome="Pessoa Editada", senha="Outra@123", perfil="COZINHA", ativo=True)
        editado = await self.client.patch(f"/api/admin/usuarios/{usuario['id']}", headers=self.admin, json=dados)
        self.assertEqual(editado.status_code, 200, editado.text)
        self.assertEqual(editado.json()["perfil"], "COZINHA")
        antigo = await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})
        self.assertEqual(antigo.status_code, 401)
        token = await self.entrar("pessoa", "Outra@123")
        dados.update(ativo=False, senha=None)
        desativado = await self.client.patch(f"/api/admin/usuarios/{usuario['id']}", headers=self.admin, json=dados)
        self.assertEqual(desativado.status_code, 200, desativado.text)
        self.assertFalse(desativado.json()["ativo"])
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)

    async def test_login_somente_por_usuario_sem_diferenciar_maiusculas(self):
        token = await self.entrar("  AdMiN  ")
        me = await self.client.get("/api/auth/me", headers=token)
        self.assertEqual(me.json()["nome_usuario"], "admin")
        for login, senha in (("admin@teste.local", SENHA), ("inexistente", SENHA), ("admin", "SenhaErrada")):
            resposta = await self.client.post("/api/auth/login", data={"username": login, "password": senha})
            self.assertEqual(resposta.status_code, 401)
            self.assertEqual(resposta.json()["detail"], "Usuário ou senha inválidos")

    async def test_renomear_login_preserva_senha_sessao_e_rejeita_duplicado(self):
        dados = {"nome": "Pessoa Teste", "nome_usuario": " PESSOA.TESTE ", "senha": SENHA, "perfil": "NUTRICIONISTA", "filial_ids": [self.a]}
        novo = await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)
        self.assertEqual(novo.status_code, 201, novo.text)
        usuario = novo.json()
        self.assertEqual(usuario["nome_usuario"], "pessoa.teste")
        token = await self.entrar("pessoa.teste")
        dados.update(nome_usuario="pessoa_nova", senha=None)
        rota = f"/api/admin/usuarios/{usuario['id']}"
        editado = await self.client.patch(rota, headers=self.admin, json=dados)
        self.assertEqual(editado.status_code, 200, editado.text)
        await self.entrar("PESSOA_NOVA")
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa.teste", "password": SENHA})).status_code, 401)
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).json()["nome_usuario"], "pessoa_nova")
        dados["nome_usuario"] = "AdMiN"
        self.assertEqual((await self.client.patch(rota, headers=self.admin, json=dados)).status_code, 409)
        await self.entrar("pessoa_nova")

    async def test_usuario_obrigatorio_valido_e_administrado_somente_pela_ti(self):
        dados = {"nome": "Pessoa Teste", "senha": SENHA, "perfil": "NUTRICIONISTA", "filial_ids": [self.a]}
        for valor in (None, "", "ab", "a" * 51, "com espaço", "pessoa@teste.local", "joão", ".pessoa", 123):
            resposta = await self.client.post("/api/admin/usuarios", headers=self.admin, json={**dados, "nome_usuario": valor})
            self.assertEqual(resposta.status_code, 422, (valor, resposta.text))
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)).status_code, 422)
        token = await self.entrar("gestor")
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=token, json={**dados, "nome_usuario": "pessoa"})).status_code, 403)
        self.assertEqual((await self.client.patch(f"/api/admin/usuarios/{self.admin_id}", headers=token, json={**dados, "nome_usuario": "admin"})).status_code, 403)

    async def test_nao_admin_nao_cadastra_nem_acessa_outra_unidade(self):
        for nome_usuario in ("gestor", "cozinha"):
            token = await self.entrar(nome_usuario)
            self.assertEqual((await self.client.get("/api/admin/usuarios", headers=token)).status_code, 403)
            self.assertEqual((await self.client.get(f"/api/pedidos?filial_id={self.a}", headers=token)).status_code, 200)
            self.assertEqual((await self.client.get(f"/api/pedidos?filial_id={self.b}", headers=token)).status_code, 403)
            me = (await self.client.get("/api/auth/me", headers=token)).json()
            self.assertEqual([f["id"] for f in me["filiais"]], [self.a])
        gestor = await self.entrar("gestor")
        for rota in (f"/api/gestao/dietas?filial_id={self.b}", f"/api/gestao/formularios/{self.b}/MEDICO",
                     f"/api/relatorios/sla?filial_id={self.b}", f"/api/relatorios/dietas?filial_id={self.b}"):
            self.assertEqual((await self.client.get(rota, headers=gestor)).status_code, 403, rota)

    async def test_validar_vinculos_usuario_e_proteger_conta_administradora(self):
        dados = {"nome": "Teste", "nome_usuario": "novo", "senha": SENHA, "perfil": "COZINHA", "filial_ids": []}
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)).status_code, 422)
        dados["filial_ids"] = [9999]
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)).status_code, 422)
        dados.update(nome_usuario="ADMIN", filial_ids=[self.a])
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)).status_code, 409)
        dados.update(nome="Admin", nome_usuario="admin", perfil="ADMIN_TI", ativo=False, senha=None)
        resposta = await self.client.patch(f"/api/admin/usuarios/{self.admin_id}", headers=self.admin, json=dados)
        self.assertEqual(resposta.status_code, 409)

    async def test_impressora_valida_ip_salva_e_testa_sem_imprimir(self):
        rota = f"/api/admin/filiais/{self.a}/impressora"
        invalido = await self.client.patch(rota, headers=self.admin, json={"ip_impressora": "sem-ip"})
        self.assertEqual(invalido.status_code, 422)
        salvo = await self.client.patch(rota, headers=self.admin, json={"ip_impressora": "10.0.0.30"})
        self.assertEqual(salvo.status_code, 200, salvo.text)
        renomeado = await self.client.patch(f"/api/admin/filiais/{self.a}", headers=self.admin, json={
            "nome": "Unidade A Editada", "codigo_slug": "unidade-a", "ativa": True,
        })
        self.assertEqual(renomeado.json()["ip_impressora"], "10.0.0.30")
        with patch("app.api.admin.conectar_impressora") as conexao:
            teste = await self.client.post(rota + "/testar", headers=self.admin)
            self.assertEqual(teste.status_code, 200, teste.text)
            conexao.assert_called_once_with("10.0.0.30")
        with patch("app.api.admin.conectar_impressora", side_effect=OSError):
            self.assertEqual((await self.client.post(rota + "/testar", headers=self.admin)).status_code, 502)
        removido = await self.client.patch(rota, headers=self.admin, json={"ip_impressora": None})
        self.assertEqual(removido.status_code, 200)
        self.assertEqual((await self.client.post(rota + "/testar", headers=self.admin)).status_code, 400)

    async def test_unidade_inativa_bloqueia_formulario_e_operacao(self):
        token = await self.entrar("gestor")
        resposta = await self.client.patch(f"/api/admin/filiais/{self.a}", headers=self.admin, json={
            "nome": "Unidade A", "codigo_slug": "unidade-a", "ativa": False,
        })
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual((await self.client.get("/api/public/unidade-a/config")).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/pedidos?filial_id={self.a}", headers=token)).status_code, 403)

    async def test_websocket_exige_credencial_e_vinculo_da_unidade(self):
        token = (await self.entrar("cozinha"))["Authorization"].removeprefix("Bearer ")
        with patch("app.main.SessionLocal", self.sessoes):
            anonimo = SocketTeste([])
            await ws_cozinha(anonimo, self.a)
            self.assertFalse(anonimo.aceito)
            self.assertEqual(anonimo.fechado, 1008)
            proibido = SocketTeste(["cnutri", token])
            await ws_cozinha(proibido, self.b)
            self.assertFalse(proibido.aceito)
            permitido = SocketTeste(["cnutri", token])
            await ws_cozinha(permitido, self.a)
            self.assertEqual(permitido.aceito, "cnutri")


if __name__ == "__main__":
    unittest.main()
