"""AD simulado e SQLite descartável: não conecta ao domínio ou banco do hospital."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import ssl
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.core.security import hash_senha, verificar_senha
from app.main import app
from app.models.models import Filial, Perfil, SessaoCopeira, SessaoUsuario, Usuario
from app.services import active_directory as ad

SENHA = "Teste@123"
HASH = hash_senha(SENHA)
GUID = "00112233-4455-6677-8899-aabbccddeeff"
GUID_OUTRO = "ffeeddcc-bbaa-9988-7766-554433221100"
PRINCIPAL = "pessoa@empresa.local"


class ClienteADTest(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(AD_HABILITADO=True, AD_DOMINIO="empresa.local",
            AD_SERVIDOR="dc01.empresa.local", AD_BASE_DN="", AD_CA_CERTIFICADO=None,
            AD_TIMEOUT_SEGUNDOS=5, AD_SESSAO_MINUTOS=30)
        self.patch_settings = patch.object(ad, "settings", self.config)
        self.patch_settings.start()
        self.addCleanup(self.patch_settings.stop)
        self.conexao = MagicMock()
        self.conexao.bind.return_value = True
        self.conexao.result = {"result": 0}
        self.entrada = {"type": "searchResEntry", "raw_attributes": {
            "objectGUID": [UUID(GUID).bytes_le], "userAccountControl": [b"512"],
            "userPrincipalName": [PRINCIPAL.encode()]}}
        self.conexao.response = [deepcopy(self.entrada)]
        self.patch_connection = patch.object(ad, "Connection", return_value=self.conexao)
        self.connection = self.patch_connection.start()
        self.addCleanup(self.patch_connection.stop)

    def test_ldaps_valida_certificado_hostname_sem_referrals_e_retorna_guid(self):
        self.assertEqual(ad.autenticar_ad(PRINCIPAL, "Senha da rede com mais de 12 caracteres!"), GUID)
        servidor = self.connection.call_args.args[0]
        self.assertTrue(servidor.ssl)
        self.assertEqual(servidor.port, 636)
        self.assertEqual(servidor.tls.validate, ssl.CERT_REQUIRED)
        self.assertEqual(servidor.tls.version, ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(servidor.tls.valid_names, ["dc01.empresa.local"])
        self.assertEqual(servidor.tls.sni, "dc01.empresa.local")
        self.assertFalse(self.connection.call_args.kwargs["auto_referrals"])
        self.assertEqual(self.conexao.search.call_args.args[0], "DC=empresa,DC=local")
        self.assertEqual(self.conexao.search.call_args.kwargs["size_limit"], 2)
        self.conexao.unbind.assert_called_once()

    def test_senha_vazia_nula_ou_excessiva_nao_faz_bind(self):
        for senha in ("", "abc\x00xyz", "a" * 1025):
            self.assertIsNone(ad.autenticar_ad(PRINCIPAL, senha))
        self.connection.assert_not_called()

    def test_senha_invalida_ou_conta_bloqueada_nao_libera_acesso(self):
        self.conexao.bind.return_value = False
        self.conexao.result = {"result": 49, "message": "resposta interna não deve vazar"}
        self.assertIsNone(ad.autenticar_ad(PRINCIPAL, SENHA))
        self.conexao.search.assert_not_called()
        self.conexao.unbind.assert_called_once()

    def test_certificado_invalido_ou_timeout_falha_sem_expor_detalhes(self):
        for erro in (ssl.SSLError("dados internos"), TimeoutError("dados internos")):
            self.conexao.bind.side_effect = erro
            with self.assertRaises(ad.ADIndisponivel) as ctx:
                ad.autenticar_ad(PRINCIPAL, SENHA)
            self.assertEqual(str(ctx.exception), "")

    def test_diretorio_desativado_nao_conecta(self):
        self.config.AD_HABILITADO = False
        with self.assertRaises(ad.ADIndisponivel):
            ad.autenticar_ad(PRINCIPAL, SENHA)
        self.connection.assert_not_called()

    def test_filtro_escapa_caracteres_especiais_e_base_configuravel(self):
        self.config.AD_BASE_DN = "OU=Equipe,DC=empresa,DC=local"
        ad.autenticar_ad("pessoa*)(objectClass=*)@empresa.local", SENHA)
        base, filtro = self.conexao.search.call_args.args
        self.assertEqual(base, self.config.AD_BASE_DN)
        self.assertIn(r"pessoa\2a\29\28objectClass=\2a\29@empresa.local", filtro)

    def test_consulta_ambigua_desativada_ou_identidade_divergente_rejeitada(self):
        for entradas in ([], [self.entrada, self.entrada],
            [{"type": "searchResEntry", "raw_attributes": {}}],
            [{"type": "searchResEntry", "raw_attributes": {**self.entrada["raw_attributes"], "userAccountControl": [b"514"]}}],
            [{"type": "searchResEntry", "raw_attributes": {**self.entrada["raw_attributes"], "userPrincipalName": [b"outra@empresa.local"]}}]):
            self.conexao.response = entradas
            self.assertIsNone(ad.autenticar_ad(PRINCIPAL, SENHA))

    def test_consulta_incompleta_nao_autoriza(self):
        self.conexao.result = {"result": 4}
        with self.assertRaises(ad.ADIndisponivel):
            ad.autenticar_ad(PRINCIPAL, SENHA)

    def test_configuracao_rejeita_ldap_sem_tls_e_servidor_ausente(self):
        for extras in ({"AD_HABILITADO": True}, {"AD_SERVIDOR": "ldap://dc01.empresa.local"},
            {"AD_HABILITADO": True, "AD_SERVIDOR": "dc01.empresa.local", "AD_DOMINIO": "empresa.local", "AD_CA_CERTIFICADO": "arquivo-inexistente.pem"}):
            with self.assertRaises(ValueError):
                Settings(_env_file=None, JWT_SECRET="s" * 40, **extras)


class AutenticacaoADTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessoes = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            self.a, self.b = Filial(nome="Unidade fictícia A", codigo_slug="demo-a"), Filial(nome="Unidade fictícia B", codigo_slug="demo-b")
            perfis = {n: Perfil(nome=n) for n in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA", "COPEIRA")}
            db.add_all([self.a, self.b, *perfis.values()])
            await db.flush()
            self.usuarios = {}
            for nome, perfil, origem in (("admin", "ADMIN_TI", "LOCAL"), ("local", "NUTRICIONISTA", "LOCAL"),
                ("pessoa", "NUTRICIONISTA", "AD"), ("adminad", "ADMIN_TI", "AD"), ("copeira", "COPEIRA", "AD")):
                u = Usuario(nome=nome.title(), nome_usuario=nome, senha_hash=HASH, perfil=perfis[perfil],
                    origem_autenticacao=origem, usuario_ad=f"{nome}@empresa.local" if origem == "AD" else None,
                    filiais=[] if perfil == "ADMIN_TI" else [self.a])
                db.add(u)
                await db.flush()
                self.usuarios[nome] = u.id
            await db.commit()
        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://teste")
        self.flag = patch.object(settings, "AD_HABILITADO", True)
        self.flag.start()
        self.directory = patch("app.api.auth.autenticar_ad", return_value=GUID)
        self.bind = self.directory.start()
        self.admin = await self.entrar("admin")

    async def asyncTearDown(self):
        self.directory.stop()
        self.flag.stop()
        app.dependency_overrides.clear()
        await self.client.aclose()
        await self.engine.dispose()

    async def entrar(self, nome, senha=SENHA):
        r = await self.client.post("/api/auth/login", data={"username": nome, "password": senha})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def dados(self, nome="pessoa", **extras):
        return {"nome": nome.title(), "nome_usuario": nome, "origem_autenticacao": "AD",
            "usuario_ad": f"{nome}@empresa.local", "perfil": "NUTRICIONISTA", "filial_ids": [self.a.id], **extras}

    async def test_local_permanece_valido_sem_consultar_ad(self):
        self.bind.assert_not_called()
        me = await self.client.get("/api/auth/me", headers=self.admin)
        self.assertEqual(me.json()["origem_autenticacao"], "LOCAL")
        async with self.sessoes() as db:
            self.assertTrue(verificar_senha(SENHA, (await db.get(Usuario, self.usuarios["admin"])).senha_hash))

    async def test_ad_aceita_senha_da_rede_e_aplica_perfil_unidades_e_expiracao(self):
        senha = "Senha corporativa com mais de doze caracteres!"
        token = await self.entrar("PESSOA", senha)
        self.bind.assert_called_once_with(PRINCIPAL, senha)
        me = await self.client.get("/api/auth/me", headers=token)
        self.assertEqual(me.json()["perfil"], "NUTRICIONISTA")
        self.assertEqual(me.json()["origem_autenticacao"], "AD")
        self.assertFalse(me.json()["troca_senha_obrigatoria"])
        self.assertEqual([f["id"] for f in me.json()["filiais"]], [self.a.id])
        self.assertEqual((await self.client.get(f"/api/gestao/dietas?filial_id={self.a.id}", headers=token)).status_code, 200)
        self.assertEqual((await self.client.get(f"/api/gestao/dietas?filial_id={self.b.id}", headers=token)).status_code, 403)
        self.assertEqual((await self.client.get("/api/admin/usuarios", headers=token)).status_code, 403)
        payload = jwt.decode(token["Authorization"][7:], settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        self.assertLessEqual(payload["exp"] - datetime.now(timezone.utc).timestamp(), settings.AD_SESSAO_MINUTOS * 60)
        async with self.sessoes() as db:
            u = await db.get(Usuario, self.usuarios["pessoa"])
            self.assertEqual(u.ad_object_guid, GUID)
            self.assertEqual(u.senha_hash, HASH)  # A senha recebida nunca substitui o hash local.

    async def test_sem_cadastro_ou_inativo_nao_consulta_diretorio(self):
        async with self.sessoes() as db:
            (await db.get(Usuario, self.usuarios["pessoa"])).ativo = False
            await db.commit()
        for nome in ("pessoa", "desconhecido"):
            self.assertEqual((await self.client.post("/api/auth/login", data={"username": nome, "password": SENHA})).status_code, 401)
        self.bind.assert_not_called()

    async def test_ad_falha_sem_fallback_para_senha_local(self):
        self.bind.return_value = None
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 401)
        async with self.sessoes() as db:
            self.assertIsNone((await db.get(Usuario, self.usuarios["pessoa"])).ad_object_guid)
            self.assertEqual(await db.scalar(select(func.count()).select_from(SessaoUsuario).where(SessaoUsuario.usuario_id == self.usuarios["pessoa"])), 0)

    async def test_ad_indisponivel_desativado_ou_http_nao_emite_sessao(self):
        self.bind.side_effect = ad.ADIndisponivel("detalhes internos")
        r = await self.client.post("/api/auth/login", data={"username": "pessoa", "password": "Segredo da rede"})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("Segredo", r.text)
        self.assertNotIn("detalhes internos", r.text)
        self.bind.reset_mock()
        with patch.object(settings, "AD_HABILITADO", False):
            self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 503)
        self.client.base_url = "http://teste"
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 503)
        self.bind.assert_not_called()

    async def test_guid_impede_conta_recriada_ou_outro_vinculo_do_mesmo_usuario(self):
        await self.entrar("pessoa")
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "copeira", "password": SENHA})).status_code, 401)
        self.bind.return_value = GUID_OUTRO
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 401)

    async def test_ad_sem_troca_de_senha_no_cnutri(self):
        token = await self.entrar("pessoa")
        r = await self.client.post("/api/auth/senha", headers=token, json={"senha_atual": SENHA, "nova_senha": "Nova@123"})
        self.assertEqual(r.status_code, 403)

    async def test_converter_local_para_ad_revoga_sessao_e_descarta_senha_local(self):
        token = await self.entrar("local")
        r = await self.client.patch(f"/api/admin/usuarios/{self.usuarios['local']}", headers=self.admin, json=self.dados("local"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["troca_senha_obrigatoria"])
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)
        async with self.sessoes() as db:
            self.assertFalse(verificar_senha(SENHA, (await db.get(Usuario, self.usuarios["local"])).senha_hash))

    async def test_converter_ad_para_local_exige_nova_senha_e_revoga_token(self):
        token = await self.entrar("pessoa")
        dados = self.dados(origem_autenticacao="LOCAL", usuario_ad=None)
        url = f"/api/admin/usuarios/{self.usuarios['pessoa']}"
        self.assertEqual((await self.client.patch(url, headers=self.admin, json=dados)).status_code, 422)
        r = await self.client.patch(url, headers=self.admin, json={**dados, "senha": SENHA})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["troca_senha_obrigatoria"])
        self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)
        await self.entrar("pessoa")

    async def test_protege_proprio_admin_e_ultimo_admin_local(self):
        dados = self.dados("admin", perfil="ADMIN_TI", filial_ids=[])
        url = f"/api/admin/usuarios/{self.usuarios['admin']}"
        self.assertEqual((await self.client.patch(url, headers=self.admin, json=dados)).status_code, 409)
        token_ad = await self.entrar("adminad")
        r = await self.client.patch(url, headers=token_ad, json=dados)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("administrador local", r.json()["detail"])

    async def test_cadastro_ad_sem_senha_e_sem_autoprovisionamento_ou_duplicidade(self):
        dados = self.dados("nova", usuario_ad=" NOVA@EMPRESA.LOCAL ")
        r = await self.client.post("/api/admin/usuarios", headers=self.admin, json=dados)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["usuario_ad"], "nova@empresa.local")
        self.assertNotIn("senha", r.json())
        self.assertNotIn("ad_object_guid", r.json())
        self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json={**dados, "nome_usuario": "outra"})).status_code, 409)
        for extras in ({"senha": SENHA}, {"usuario_ad": None}):
            self.assertEqual((await self.client.post("/api/admin/usuarios", headers=self.admin, json={**self.dados("invalida"), **extras})).status_code, 422)
        self.bind.assert_not_called()

    async def test_edicao_de_perfil_preserva_vinculo_guid_sem_exigir_senha(self):
        await self.entrar("pessoa")
        r = await self.client.patch(f"/api/admin/usuarios/{self.usuarios['pessoa']}", headers=self.admin,
            json=self.dados(perfil="COZINHA", filial_ids=[self.b.id]))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["perfil"], "COZINHA")
        async with self.sessoes() as db:
            self.assertEqual((await db.get(Usuario, self.usuarios["pessoa"])).ad_object_guid, GUID)

    async def test_copeira_ad_tem_presenca_e_desativar_integracao_invalida_token(self):
        token = await self.entrar("copeira")
        self.assertEqual((await self.client.post("/api/auth/presenca", headers=token, json={"filial_id": self.a.id})).status_code, 200)
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(SessaoCopeira)), 1)
        with patch.object(settings, "AD_HABILITADO", False):
            self.assertEqual((await self.client.get("/api/auth/me", headers=token)).status_code, 401)

    async def test_limite_de_tentativas_tambem_protege_ad(self):
        self.bind.return_value = None
        for _ in range(5):
            self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 401)
        self.assertEqual((await self.client.post("/api/auth/login", data={"username": "pessoa", "password": SENHA})).status_code, 429)
        self.assertEqual(self.bind.call_count, 5)

    async def test_situacao_ad_restrita_a_administradores(self):
        r = await self.client.get("/api/admin/autenticacao-ad", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {"habilitado", "configurado", "dominio", "servidor", "sessao_minutos"})
        token = await self.entrar("local")
        self.assertEqual((await self.client.get("/api/admin/autenticacao-ad", headers=token)).status_code, 403)
