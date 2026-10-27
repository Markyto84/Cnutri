"""Regressões da revisão de 27/10: etapas e cancelamento antes da impressão, sem papel real."""
import asyncio
import os
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event, func, select

import test_cozinha_sem_login as fixtures
from app.core.sessoes import emitir_sessao
from app.models.models import EventoAssistencial, Filial, HistoricoPedido, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.fila_impressao import processar_um


class RevisaoFluxosTest(unittest.IsolatedAsyncioTestCase):
    fixture = fixtures.CozinhaSemLoginTest

    async def asyncSetUp(self):
        self.f = self.fixture('test_fluxo_completo_sem_login_e_sem_pular_etapa')
        await self.f.asyncSetUp()

    async def asyncTearDown(self):
        await self.f.asyncTearDown()

    async def novo_pedido(self, status='PENDENTE'):
        async with self.f.sessoes() as db:
            pedido = Pedido(filial_id=self.f.a, tipo_solicitacao='MEDICO', status=status,
                solicitante_identificacao='CRM TESTE', solicitante_nome='Profissional fictício', dados_dinamicos={})
            db.add(pedido)
            await db.commit()
            return pedido.id

    def url(self, rota, pedido_id):
        if rota == 'legada':
            return f'/api/pedidos/{pedido_id}/status'
        return f'/api/{rota}/unidades/{self.f.a}/pedidos/{pedido_id}/status'

    async def test_matriz_de_etapas_igual_nas_tres_rotas_preserva_estado_e_auditoria(self):
        for rota in ('legada', 'operacao', 'cozinha'):
            headers = {'Authorization': 'Bearer expirado'} if rota == 'cozinha' else self.f.admin
            for anterior in ('PENDENTE', 'EM_PREPARO', 'PRONTO', 'CANCELADO', 'ENTREGUE'):
                for novo in ('PENDENTE', 'EM_PREPARO', 'PRONTO', 'CANCELADO'):
                    with self.subTest(rota=rota, anterior=anterior, novo=novo):
                        pedido_id = await self.novo_pedido(anterior)
                        ativo = anterior in ('PENDENTE', 'EM_PREPARO', 'PRONTO')
                        permitido = ativo and (anterior == novo or novo == 'CANCELADO'
                            or (anterior, novo) in (('PENDENTE', 'EM_PREPARO'), ('EM_PREPARO', 'PRONTO')))
                        alterou = permitido and anterior != novo
                        r = await self.f.cliente.patch(self.url(rota, pedido_id), headers=headers,
                            json={'status': novo, 'motivo': '  Cancelamento fictício  '})
                        self.assertEqual(r.status_code, 200 if permitido else 409, r.text)
                        async with self.f.sessoes() as db:
                            pedido = await db.get(Pedido, pedido_id)
                            self.assertEqual(pedido.status, novo if permitido else anterior)
                            self.assertEqual(pedido.concluido_em is not None, alterou and novo == 'PRONTO')
                            historico = (await db.scalars(select(HistoricoPedido).where(HistoricoPedido.pedido_id == pedido_id))).all()
                            eventos = (await db.scalars(select(EventoAssistencial).where(EventoAssistencial.pedido_id == pedido_id))).all()
                            self.assertEqual(len(historico), int(alterou))
                            self.assertEqual(len(eventos), int(alterou))
                            if alterou:
                                self.assertEqual((historico[0].status_anterior, historico[0].status_novo), (anterior, novo))
                                self.assertEqual(eventos[0].motivo, 'Cancelamento fictício' if novo == 'CANCELADO' else None)
                                self.assertEqual(eventos[0].autor_usuario_id is None, rota == 'cozinha')

    async def test_rota_legada_preserva_autenticacao_perfil_e_unidade(self):
        rota = self.url('legada', self.f.ids['PENDENTE'])
        for headers in ({}, {'Authorization': 'Bearer expirado'}):
            self.assertEqual((await self.f.cliente.patch(rota, headers=headers, json={'status': 'EM_PREPARO'})).status_code, 401)
        for perfil, filial in (('NUTRICIONISTA', self.f.b), ('COPEIRA', self.f.a), ('COZINHA', self.f.a)):
            async with self.f.sessoes() as db:
                pessoa = Usuario(nome='Pessoa fictícia', nome_usuario='teste-' + uuid4().hex,
                    senha_hash='NAO-UTILIZADO', perfil=Perfil(nome=perfil), filiais=[await db.get(Filial, filial)])
                db.add(pessoa)
                await db.flush()
                token = (await emitir_sessao(db, pessoa)).access_token
                await db.commit()
            r = await self.f.cliente.patch(rota, headers={'Authorization': 'Bearer ' + token}, json={'status': 'EM_PREPARO'})
            self.assertEqual(r.status_code, 200 if perfil == 'COZINHA' else 403, r.text)

    async def test_cancelamento_durante_preparacao_da_filipeta_impede_transmissao(self):
        r = await self.f.cliente.post(self.f.rota('PENDENTE', 'reimprimir'))
        self.assertEqual(r.status_code, 202, r.text)
        job_id = r.json()['impressao']['id']

        async def preparar(*_args):
            cancelamento = await self.f.cliente.patch(self.f.rota('PENDENTE'),
                json={'status': 'CANCELADO', 'motivo': 'Cancelamento fictício antes do envio'})
            self.assertEqual(cancelamento.status_code, 200, cancelamento.text)
            return b'DOCUMENTO FICTICIO'

        with patch('app.services.fila_impressao.montar_filipeta_configurada', side_effect=preparar), \
                patch('app.services.fila_impressao.enviar_filipeta') as transporte:
            self.assertTrue(await processar_um(self.f.sessoes))
            self.assertFalse(await processar_um(self.f.sessoes))
            transporte.assert_not_called()
        async with self.f.sessoes() as db:
            pedido = await db.get(Pedido, self.f.ids['PENDENTE'])
            job = await db.get(TrabalhoImpressao, job_id)
            self.assertEqual(pedido.status, 'CANCELADO')
            self.assertEqual(job.estado, 'CANCELADO')
            self.assertIsNone(job.enviado_em)
            self.assertIsNone(job.reserva)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido).where(HistoricoPedido.impresso.is_(True))), 0)

    async def test_cancelado_nao_enfileira_novas_filipetas_em_nenhuma_rota(self):
        pedido_id = self.f.ids['CANCELADO']
        for rota in ('legada', 'operacao', 'cozinha'):
            r = await self.f.cliente.post(self.url(rota, pedido_id).replace('/status', '/reimprimir'),
                headers={} if rota == 'cozinha' else self.f.admin)
            self.assertEqual(r.status_code, 409, r.text)
        async with self.f.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao)), 0)


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_POSTGRES_URL'), 'Requer PostgreSQL de teste')
class RevisaoFluxosPostgresTest(RevisaoFluxosTest):
    fixture = fixtures.CozinhaSemLoginPostgresTest

    async def test_cancelamento_confirmado_enquanto_fila_aguarda_bloqueio_impede_envio(self):
        r = await self.f.cliente.post(self.f.rota('PENDENTE', 'reimprimir'))
        self.assertEqual(r.status_code, 202, r.text)
        job_id = r.json()['impressao']['id']
        # Documento já persistido: o retry deve executar a mesma validação final.
        async with self.f.sessoes() as db:
            (await db.get(TrabalhoImpressao, job_id)).dados = b'DOCUMENTO FICTICIO EM CACHE'
            await db.commit()
        esperando = asyncio.Event()

        def consulta_final(_conn, _cursor, sql, _params, _context, _many):
            if 'SELECT pedidos.status' in sql and 'FOR UPDATE' in sql:
                esperando.set()

        tarefa = None
        async with self.f.sessoes() as cancelamento:
            pedido = await cancelamento.scalar(select(Pedido).where(Pedido.id == self.f.ids['PENDENTE']).with_for_update())
            pedido.status = 'CANCELADO'
            await cancelamento.flush()
            event.listen(self.f.motor.sync_engine, 'before_cursor_execute', consulta_final)
            try:
                with patch('app.services.fila_impressao.enviar_filipeta') as transporte:
                    tarefa = asyncio.create_task(processar_um(self.f.sessoes))
                    await asyncio.wait_for(esperando.wait(), 5)
                    self.assertFalse(tarefa.done())
                    transporte.assert_not_called()
                    await cancelamento.commit()
                    await asyncio.wait_for(tarefa, 5)
                    transporte.assert_not_called()
            finally:
                event.remove(self.f.motor.sync_engine, 'before_cursor_execute', consulta_final)
                if tarefa and not tarefa.done():
                    tarefa.cancel()
                    await asyncio.gather(tarefa, return_exceptions=True)
        async with self.f.sessoes() as db:
            job = await db.get(TrabalhoImpressao, job_id)
            self.assertEqual(job.estado, 'CANCELADO')
            self.assertIsNone(job.enviado_em)

    async def test_cancelamento_aguarda_filipeta_ja_em_transmissao_e_nao_duplica(self):
        r = await self.f.cliente.post(self.f.rota('PENDENTE', 'reimprimir'))
        self.assertEqual(r.status_code, 202, r.text)
        job_id = r.json()['impressao']['id']
        enviando, liberar, cancelando = asyncio.Event(), threading.Event(), asyncio.Event()
        loop = asyncio.get_running_loop()

        def transmitir(*_args):
            loop.call_soon_threadsafe(enviando.set)
            if not liberar.wait(5):
                raise RuntimeError('Transporte de teste não foi liberado')

        def atualizando(_conn, _cursor, sql, _params, _context, _many):
            if sql.startswith('UPDATE pedidos SET status='):
                cancelando.set()

        tarefas = []
        event.listen(self.f.motor.sync_engine, 'before_cursor_execute', atualizando)
        try:
            with patch('app.services.fila_impressao.enviar_filipeta', side_effect=transmitir) as transporte:
                tarefas.append(asyncio.create_task(processar_um(self.f.sessoes)))
                await asyncio.wait_for(enviando.wait(), 5)
                tarefas.append(asyncio.create_task(self.f.cliente.patch(self.f.rota('PENDENTE'),
                    json={'status': 'CANCELADO', 'motivo': 'Cancelamento fictício durante envio'})))
                await asyncio.wait_for(cancelando.wait(), 5)
                self.assertFalse(tarefas[1].done(), 'Cancelamento foi confirmado durante a transmissão')
                liberar.set()
                _, resposta = await asyncio.wait_for(asyncio.gather(*tarefas), 5)
                self.assertEqual(resposta.status_code, 200, resposta.text)
                self.assertFalse(await processar_um(self.f.sessoes))
                transporte.assert_called_once()
        finally:
            liberar.set()
            event.remove(self.f.motor.sync_engine, 'before_cursor_execute', atualizando)
            for tarefa in tarefas:
                if not tarefa.done():
                    tarefa.cancel()
            await asyncio.gather(*tarefas, return_exceptions=True)
        async with self.f.sessoes() as db:
            self.assertEqual((await db.get(Pedido, self.f.ids['PENDENTE'])).status, 'CANCELADO')
            job = await db.get(TrabalhoImpressao, job_id)
            self.assertEqual(job.estado, 'ENVIADO')
            self.assertIsNotNone(job.enviado_em)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido).where(HistoricoPedido.impresso.is_(True))), 1)
