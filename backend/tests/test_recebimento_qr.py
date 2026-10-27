"""Recebimento público de uma refeição, em bancos descartáveis e sem impressoras físicas."""
import asyncio
import os
import unittest
from unittest.mock import patch

from sqlalchemy import event, func, select

import test_cozinha_sem_login as fixtures
from app.core.config import settings
from app.models.models import EventoAssistencial, Filial, FormularioConfig, HistoricoPedido, Pedido, RecebimentoQR
from app.services.impressora import compor_linhas_filipeta
from app.services.impressao_raster import renderizar_filipeta, LinhaImpressao
from app.services.recebimento_qr import endereco_recebimento, preparar_codigo
from pydantic import ValidationError
from app.core.config import Settings


class ConfiguracaoQRTest(unittest.TestCase):
    def test_endereco_publico_exige_origem_http_valida_sem_credenciais_ou_parametros(self):
        argumentos = {'_env_file': None, 'JWT_SECRET': 'TESTE-SEM-SEGREDO-' * 3, 'APP_ENV': 'test'}
        valido = Settings(**argumentos, URL_RECEBIMENTO_PUBLICA='https://cnutri.empresa.local/')
        self.assertEqual(valido.URL_RECEBIMENTO_PUBLICA, 'https://cnutri.empresa.local')
        for url in ('file:///teste', 'http://usuario:senha@servidor.local', 'https://servidor.local/admin',
            'https://servidor.local?token=1', 'http://servidor.local:abc', 'http://servidor.local:0'):
            with self.assertRaises(ValidationError):
                Settings(**argumentos, URL_RECEBIMENTO_PUBLICA=url)


class RecebimentoQRTest(unittest.IsolatedAsyncioTestCase):
    fixture = fixtures.CozinhaSemLoginTest

    async def asyncSetUp(self):
        self.f = self.fixture('test_fluxo_completo_sem_login_e_sem_pular_etapa')
        await self.f.asyncSetUp()
        self.config = patch.object(settings, 'URL_RECEBIMENTO_PUBLICA', 'https://cnutri.test')
        self.config.start()
        async with self.f.sessoes() as db:
            for tipo in ('MEDICO', 'ENFERMAGEM'):
                db.add(FormularioConfig(filial_id=self.f.a, tipo_publico=tipo, esquema_json={'campos': []}))
            await db.commit()

    async def asyncTearDown(self):
        self.config.stop()
        await self.f.asyncTearDown()

    def payload(self, paciente=False):
        return {'tipo_solicitacao': 'PACIENTE' if paciente else 'MEDICO', 'solicitante_nome': 'Solicitante fictício',
            'solicitante_identificacao': 'REGISTRO PRIVADO', 'nome_paciente': 'Paciente fictício' if paciente else None}

    async def criar(self, status='PENDENTE', paciente=False):
        r = await self.f.cliente.post('/api/public/a/pedidos', json=self.payload(paciente))
        self.assertEqual(r.status_code, 201, r.text)
        pedido = r.json()['id']
        for etapa in (() if status == 'PENDENTE' else ('EM_PREPARO',) if status == 'EM_PREPARO' else ('EM_PREPARO', 'PRONTO')):
            r = await self.f.cliente.patch(f'{self.f.base}/pedidos/{pedido}/status', json={'status': etapa})
            self.assertEqual(r.status_code, 200, r.text)
        async with self.f.sessoes() as db:
            codigo = await db.get(RecebimentoQR, pedido)
            return pedido, codigo.codigo

    async def confirmar(self, codigo, registro='COREN-SP 123456'):
        return await self.f.cliente.post('/api/recebimentos/confirmar', json={'codigo': codigo, 'registro_profissional': registro},
            headers={'Authorization': 'Bearer expirado'})

    async def test_criacao_emite_codigo_exclusivo_consulta_publica_nao_expoe_dados_clinicos(self):
        pedido, codigo = await self.criar(paciente=True)
        _, outro = await self.criar()
        self.assertNotEqual(codigo, outro)
        self.assertEqual(len(codigo), 43)
        r = await self.f.cliente.post('/api/recebimentos/consultar', json={'codigo': codigo}, headers={'Authorization': 'Bearer expirado'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(set(r.json()), {'pedido_id', 'unidade', 'status', 'pode_confirmar', 'confirmado_em'})
        self.assertEqual(r.json()['pedido_id'], pedido)
        self.assertFalse(r.json()['pode_confirmar'])
        self.assertNotIn('Paciente', r.text)
        self.assertNotIn('PRIVADO', r.text)
        painel = await self.f.cliente.get(self.f.base + '/estado')
        atual = next(p for p in painel.json()['pedidos'] if p['id'] == pedido)
        self.assertTrue(atual['recebimento_qr'])
        self.assertNotIn(codigo, painel.text)

    async def test_so_confirma_pronto_e_registro_e_horario_nao_sao_sobrescritos(self):
        pedido, codigo = await self.criar()
        self.assertEqual((await self.confirmar(codigo)).status_code, 409)
        r = await self.f.cliente.patch(f'{self.f.base}/pedidos/{pedido}/status', json={'status': 'EM_PREPARO'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((await self.confirmar(codigo)).status_code, 409)
        await self.f.cliente.patch(f'{self.f.base}/pedidos/{pedido}/status', json={'status': 'PRONTO'})
        for registro in ('', '   ', 'a', 'COREN', '123\nABC', 'A' * 51, '=12345'):
            r = await self.confirmar(codigo, registro)
            self.assertEqual(r.status_code, 422, r.text)
        primeira = await self.confirmar(codigo, '  coren-sp 123456  ')
        self.assertEqual(primeira.status_code, 200, primeira.text)
        self.assertEqual(primeira.json()['status'], 'ENTREGUE')
        self.assertIsNotNone(primeira.json()['confirmado_em'])
        repetida = await self.confirmar(codigo, 'CRM 98765')
        self.assertEqual(repetida.json(), primeira.json())
        async with self.f.sessoes() as db:
            recebido = await db.get(RecebimentoQR, pedido)
            self.assertEqual(recebido.registro_profissional, 'COREN-SP 123456')
            self.assertIsNotNone(recebido.confirmado_em)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido).where(HistoricoPedido.pedido_id == pedido,
                HistoricoPedido.status_novo == 'ENTREGUE')), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(EventoAssistencial).where(EventoAssistencial.acao == 'ENTREGA_CONFIRMADA_QR')), 1)
        adulterada = await self.f.cliente.post('/api/recebimentos/confirmar', json={'codigo': codigo,
            'registro_profissional': 'CRM 1234', 'confirmado_em': '2000-01-01', 'pedido_id': 1})
        self.assertEqual(adulterada.status_code, 422)

    async def test_cancelado_unidade_inativa_e_codigo_desconhecido_nao_confirmam(self):
        pedido, codigo = await self.criar('PRONTO')
        r = await self.f.cliente.patch(f'{self.f.base}/pedidos/{pedido}/status', json={'status': 'CANCELADO', 'motivo': 'Cancelamento fictício'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((await self.confirmar(codigo)).status_code, 409)
        self.assertEqual((await self.confirmar('x' * 43)).status_code, 404)
        async with self.f.sessoes() as db:
            self.assertIsNone((await db.get(RecebimentoQR, pedido)).confirmado_em)
            (await db.get(Filial, self.f.a)).ativa = False
            await db.commit()
        self.assertEqual((await self.confirmar(codigo)).status_code, 404)

    async def test_correcao_do_pedido_invalida_qr_anterior_e_gera_outro(self):
        pedido, anterior = await self.criar(paciente=True)
        dados = {**self.payload(True), 'nome_paciente': 'Paciente fictício corrigido'}
        r = await self.f.cliente.put(f'/api/assistencia/pedidos/{pedido}', headers=self.f.admin,
            json={'versao': 1, 'motivo': 'Correção fictícia do destinatário', 'pedido': dados})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.confirmar(anterior)).status_code, 404)
        async with self.f.sessoes() as db:
            codigo = await db.get(RecebimentoQR, pedido)
            self.assertNotEqual(codigo.codigo, anterior)
            self.assertEqual(codigo.versao, 2)

    async def test_qr_bloqueia_finalizacao_manual_e_consta_nos_relatorios_e_exportacoes(self):
        pedido, codigo = await self.criar('PRONTO', paciente=True)
        manual = await self.f.cliente.post(f'/api/operacao/unidades/{self.f.a}/pedidos/{pedido}/entregar',
            headers=self.f.admin, json={'copeira_id': 1})
        self.assertEqual(manual.status_code, 409, manual.text)
        self.assertIn('QR Code', manual.text)
        self.assertEqual((await self.confirmar(codigo)).status_code, 200)
        entregas = await self.f.cliente.get('/api/relatorios/entregas', headers=self.f.admin, params={'filial_id': self.f.a})
        self.assertEqual(entregas.status_code, 200, entregas.text)
        item = next(p for p in entregas.json()['itens'] if p['pedido_id'] == pedido)
        self.assertEqual(item['recebedor_registro_profissional'], 'COREN-SP 123456')
        self.assertEqual(item['origem_entrega'], 'QR Code')
        self.assertFalse(item['assinatura_disponivel'])
        self.assertIsNone(item['copeira_nome'])
        filtro = {'inicio': '2020-01-01T00:00:00Z', 'fim': '2100-01-01T00:00:00Z', 'data_base': 'entrega'}
        detalhes = await self.f.cliente.get('/api/relatorios/dietas-periodo', headers=self.f.admin, params=filtro)
        self.assertEqual(detalhes.status_code, 200, detalhes.text)
        self.assertEqual(detalhes.json()['totais']['entregues'], 1)
        self.assertEqual(detalhes.json()['itens'][0]['recebedor_registro_profissional'], 'COREN-SP 123456')
        csv = await self.f.cliente.get('/api/relatorios/dietas-periodo/exportar', headers=self.f.admin, params={**filtro, 'formato': 'csv'})
        self.assertEqual(csv.status_code, 200, csv.text)
        self.assertIn('Registro profissional do recebedor', csv.text)
        self.assertIn('COREN-SP 123456', csv.text)
        detalhe = await self.f.cliente.get(f'/api/assistencia/pedidos/{pedido}', headers=self.f.admin)
        self.assertEqual(detalhe.json()['entrega']['recebedor_registro_profissional'], 'COREN-SP 123456')

    async def test_filipeta_substitui_assinatura_por_qr_sem_alterar_campos_da_refeicao(self):
        pedido, _ = await self.criar()
        async with self.f.sessoes() as db:
            registro = await db.get(RecebimentoQR, pedido)
            dados = await db.get(Pedido, pedido)
            linhas = compor_linhas_filipeta(dados, 'Unidade fictícia', url_recebimento=endereco_recebimento(registro))
        textos = '\n'.join(l.texto for l in linhas)
        self.assertNotIn('Assinatura:', textos)
        self.assertNotIn('Data e hora:', textos)
        self.assertIn('ENTREGA', textos)
        self.assertEqual(sum(l.url_qr is not None for l in linhas), 1)
        imagem = renderizar_filipeta(linhas)
        self.assertEqual(imagem.width, 576)
        self.assertGreater(imagem.height, 300)


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_POSTGRES_URL'), 'Requer PostgreSQL de teste')
class RecebimentoQRPostgresTest(RecebimentoQRTest):
    fixture = fixtures.CozinhaSemLoginPostgresTest

    async def test_entrega_manual_rele_qr_criado_por_reimpressao_concorrente(self):
        pedido_id = self.f.ids['PRONTO']
        esperando = asyncio.Event()
        def bloqueando(_conn, _cursor, sql, _params, _context, _many):
            if sql.startswith('SELECT pedidos.id') and 'FOR UPDATE' in sql:
                esperando.set()
        tarefa = None
        async with self.f.sessoes() as reimpressao:
            pedido = await reimpressao.scalar(select(Pedido).where(Pedido.id == pedido_id).with_for_update())
            await preparar_codigo(reimpressao, pedido)
            event.listen(self.f.motor.sync_engine, 'before_cursor_execute', bloqueando)
            try:
                tarefa = asyncio.create_task(self.f.cliente.post(f'/api/operacao/unidades/{self.f.a}/pedidos/{pedido_id}/entregar',
                    headers=self.f.admin, json={'copeira_id': 1}))
                await asyncio.wait_for(esperando.wait(), 5)
                self.assertFalse(tarefa.done())
                await reimpressao.commit()
                resposta = await asyncio.wait_for(tarefa, 5)
                self.assertEqual(resposta.status_code, 409, resposta.text)
                self.assertIn('QR Code', resposta.text)
            finally:
                event.remove(self.f.motor.sync_engine, 'before_cursor_execute', bloqueando)
                if tarefa and not tarefa.done():
                    tarefa.cancel()
                    await asyncio.gather(tarefa, return_exceptions=True)

    async def test_duas_confirmacoes_simultaneas_mantem_um_registro_e_mesmo_horario(self):
        pedido, codigo = await self.criar('PRONTO')
        respostas = await asyncio.gather(self.confirmar(codigo, 'COREN 123'), self.confirmar(codigo, 'CRM 456'))
        self.assertEqual([r.status_code for r in respostas], [200, 200], [r.text for r in respostas])
        self.assertEqual(respostas[0].json()['confirmado_em'], respostas[1].json()['confirmado_em'])
        async with self.f.sessoes() as db:
            self.assertIn((await db.get(RecebimentoQR, pedido)).registro_profissional, ('COREN 123', 'CRM 456'))
            self.assertEqual(await db.scalar(select(func.count()).select_from(EventoAssistencial).where(EventoAssistencial.acao == 'ENTREGA_CONFIRMADA_QR')), 1)

    async def test_cancelamento_concorrente_nunca_resulta_em_cancelado_com_entrega_confirmada(self):
        pedido, codigo = await self.criar('PRONTO')
        recebimento, cancelamento = await asyncio.gather(self.confirmar(codigo), self.f.cliente.patch(
            f'{self.f.base}/pedidos/{pedido}/status', json={'status': 'CANCELADO', 'motivo': 'Cancelamento fictício concorrente'}))
        self.assertEqual(sorted([recebimento.status_code, cancelamento.status_code]), [200, 409])
        async with self.f.sessoes() as db:
            atual = await db.get(Pedido, pedido)
            qr = await db.get(RecebimentoQR, pedido)
            self.assertEqual(qr.confirmado_em is not None, atual.status == 'ENTREGUE')
