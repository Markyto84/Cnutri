"""Códigos e listagem pública em SQLite/PostgreSQL exclusivos, sem dados reais."""
import os
import unittest

from sqlalchemy import func, select

import test_cozinha_sem_login as fixtures
from app.models.models import AuditoriaAdministrativa, Filial, FormularioConfig
from app.schemas.schemas import FilialOut


class EnderecosUnidadesTest(unittest.IsolatedAsyncioTestCase):
    fixture = fixtures.CozinhaSemLoginTest

    async def asyncSetUp(self):
        self.f = self.fixture('test_fluxo_completo_sem_login_e_sem_pular_etapa')
        await self.f.asyncSetUp()

    async def asyncTearDown(self):
        await self.f.asyncTearDown()

    async def test_codigos_conflitantes_sao_recusados_na_criacao_e_edicao_sem_gravar(self):
        reservados = ('login', 'admin', 'gestao', 'senha', 'sem-unidades', 'cozinha', 'entregas', 'api', 'ws', 'src', 'assets')
        invalidos = ('2', '0001', '12-34', '', '  ', 'unidade/invalida', 'unidade?', 'Maiuscula', None, 123, 'a' * 51)
        for codigo in (*reservados, *invalidos):
            for criar in (True, False):
                with self.subTest(codigo=codigo, criar=criar):
                    metodo = self.f.cliente.post if criar else self.f.cliente.patch
                    url = '/api/admin/filiais' if criar else f'/api/admin/filiais/{self.f.a}'
                    r = await metodo(url, headers=self.f.admin, json={'nome': 'Unidade fictícia', 'codigo_slug': codigo})
                    self.assertEqual(r.status_code, 422, r.text)
                    self.assertEqual(r.json()['detail'][0]['loc'][-1], 'codigo_slug')
                    if codigo in reservados:
                        self.assertIn('reservado', r.json()['detail'][0]['msg'])
        async with self.f.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(Filial)), 2)
            self.assertEqual((await db.get(Filial, self.f.a)).codigo_slug, 'a')
            self.assertEqual(await db.scalar(select(func.count()).select_from(FormularioConfig)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(AuditoriaAdministrativa)), 0)

    async def test_codigos_validos_sao_preservados_e_links_resolvem_a_unidade_correta(self):
        for codigo in ('unidade-sul', '21-unidade', 'apice-hospital', 'ws-havai', 'assets-sul', 'a' * 50):
            r = await self.f.cliente.post('/api/admin/filiais', headers=self.f.admin,
                json={'nome': 'Unidade fictícia', 'codigo_slug': ' ' + codigo + ' '})
            self.assertEqual(r.status_code, 201, r.text)
            nova = r.json()
            self.assertEqual(nova['codigo_slug'], codigo)
            painel = await self.f.cliente.get(f'/api/cozinha/unidades/{codigo}/estado')
            self.assertEqual(painel.status_code, 200, painel.text)
            self.assertEqual(painel.json()['filial_id'], nova['id'])
            config = await self.f.cliente.get(f'/api/public/{codigo}/config')
            self.assertEqual(config.status_code, 200, config.text)
            self.assertEqual(config.json()['filial']['id'], nova['id'])
            self.assertEqual((await self.f.cliente.get(f'/api/cozinha/unidades/{nova["id"]}/estado')).json()['filial_id'], nova['id'])
        repetida = await self.f.cliente.post('/api/admin/filiais', headers=self.f.admin,
            json={'nome': 'Duplicada fictícia', 'codigo_slug': 'unidade-sul'})
        self.assertEqual(repetida.status_code, 409, repetida.text)
        editada = await self.f.cliente.patch(f'/api/admin/filiais/{self.f.a}', headers=self.f.admin,
            json={'nome': 'Unidade fictícia renomeada', 'codigo_slug': 'unidade-renomeada'})
        self.assertEqual(editada.status_code, 200, editada.text)
        self.assertEqual(editada.json()['id'], self.f.a)
        self.assertEqual((await self.f.cliente.get('/api/cozinha/unidades/unidade-renomeada/estado')).json()['filial_id'], self.f.a)
        self.assertEqual((await self.f.cliente.get(self.f.base + '/estado')).json()['filial_id'], self.f.a)

    async def test_unidade_antiga_conflitante_continua_consultavel_para_ti_corrigir(self):
        async with self.f.sessoes() as db:
            filial = await db.get(Filial, self.f.b)
            filial.codigo_slug = 'login'
            await db.commit()
            self.assertEqual(FilialOut.model_validate(filial).codigo_slug, 'login')
        lista = await self.f.cliente.get('/api/admin/filiais', headers=self.f.admin)
        self.assertEqual(lista.status_code, 200, lista.text)
        self.assertTrue(any(f['id'] == self.f.b and f['codigo_slug'] == 'login' for f in lista.json()))
        alterada = await self.f.cliente.patch(f'/api/admin/filiais/{self.f.b}', headers=self.f.admin,
            json={'nome': 'Unidade fictícia B', 'codigo_slug': 'unidade-b-corrigida'})
        self.assertEqual(alterada.status_code, 200, alterada.text)

    async def test_lista_publica_sem_sessao_ou_com_sessao_expirada_so_exibe_unidades_ativas(self):
        for quantidade in (2, 1, 0):
            if quantidade < 2:
                async with self.f.sessoes() as db:
                    (await db.get(Filial, self.f.b if quantidade == 1 else self.f.a)).ativa = False
                    await db.commit()
            for headers in ({}, {'Authorization': 'Bearer expirado'}):
                r = await self.f.cliente.get('/api/operacao/unidades', headers=headers)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(len(r.json()), quantidade)
                self.assertTrue(all(set(f) == {'id', 'nome', 'codigo_slug'} for f in r.json()))
                self.assertNotIn('192.0.2.', r.text)
                self.assertNotIn('Paciente', r.text)


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_POSTGRES_URL'), 'Requer PostgreSQL de teste')
class EnderecosUnidadesPostgresTest(EnderecosUnidadesTest):
    fixture = fixtures.CozinhaSemLoginPostgresTest
