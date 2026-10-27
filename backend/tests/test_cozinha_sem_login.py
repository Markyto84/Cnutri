"""Operação da cozinha sem sessão, em bancos isolados e sem impressão física."""
import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.database import Base, get_db
from app.core.sessoes import emitir_sessao
from app.core.ws import ConnectionManager
from app.main import app, ws_cozinha_publica
from app.models.models import Dieta, EventoAssistencial, Filial, HistoricoPedido, ImpressoraEtiqueta, Pedido, Perfil, TrabalhoImpressao, Usuario
from app.services.contexto_operacao import MonitorContexto


class Socket:
    def __init__(self):
        self.mensagens, self.fechado, self.aceito = [], None, False
        self.recebidas = iter(['ping'])

    async def accept(self, **kwargs):
        self.aceito = True

    async def send_json(self, mensagem):
        self.mensagens.append(mensagem)

    async def close(self, code=1000):
        self.fechado = code

    async def receive_text(self):
        try:
            return next(self.recebidas)
        except StopIteration:
            raise RuntimeError('Fim do teste') from None


class CozinhaSemLoginTest(unittest.IsolatedAsyncioTestCase):
    async def criar_engine(self):
        return create_async_engine('sqlite+aiosqlite:///:memory:')

    async def asyncSetUp(self):
        self.motor = await self.criar_engine()
        self.sessoes = async_sessionmaker(self.motor, expire_on_commit=False)
        async with self.motor.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with self.sessoes() as db:
            a, b = Filial(nome='Unidade fictícia A', codigo_slug='a', ip_impressora='192.0.2.10'), Filial(nome='Unidade fictícia B', codigo_slug='b')
            db.add_all([a, b]); await db.flush()
            self.a, self.b = a.id, b.id
            dieta = Dieta(nome='GERAL', filial_id=a.id)
            admin = Usuario(nome='TI Fictícia', nome_usuario='ti', perfil=Perfil(nome='ADMIN_TI'), senha_hash='NAO-UTILIZADO')
            db.add_all([dieta, admin, ImpressoraEtiqueta(filial_id=a.id, ip='192.0.2.20')]); await db.flush()
            self.ids = {}
            for etapa in ('PENDENTE', 'EM_PREPARO', 'PRONTO', 'ENTREGUE', 'CANCELADO'):
                p = Pedido(filial_id=a.id, tipo_solicitacao='PACIENTE', solicitante_identificacao='REGISTRO PRIVADO',
                    solicitante_nome='Solicitante fictício', nome_paciente='Paciente fictício', prontuario='PRONTUARIO PRIVADO',
                    dieta_id=dieta.id, status=etapa, dados_dinamicos={'refeicao': 'ALMOÇO', 'andar': 'TÉRREO',
                        'matricula': 'MATRICULA PRIVADA', 'data_nascimento': '1970-01-01', 'sexo': 'PRIVADO',
                        'cardapio': 'Refeição fictícia', 'liquido_espessado': 'Sim', 'tipo_liquido_espessado': 'NÉCTAR'})
                db.add(p); await db.flush(); self.ids[etapa] = p.id
            self.admin = {'Authorization': 'Bearer ' + (await emitir_sessao(db, admin)).access_token}
            await db.commit()

        async def banco():
            async with self.sessoes() as db:
                yield db
        app.dependency_overrides[get_db] = banco
        self.cliente = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://teste')
        self.base = f'/api/cozinha/unidades/{self.a}'

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.cliente.aclose()
        await self.motor.dispose()
        if hasattr(self, 'admin_engine'):
            async with self.admin_engine.begin() as c:
                await c.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')
            await self.admin_engine.dispose()

    def rota(self, etapa, final='status'):
        return f'{self.base}/pedidos/{self.ids[etapa]}/{final}'

    async def test_estado_operacional_sem_token_e_com_token_expirado_mantem_reconciliacao(self):
        r = await self.cliente.get(self.base + '/estado')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()['pedidos']), 3)
        self.assertEqual(r.json()['copeiras'], [])
        for valor in ('Paciente fictício', 'GERAL', 'Refeição fictícia', 'NÉCTAR'):
            self.assertIn(valor, r.text)
        for valor in ('REGISTRO PRIVADO', 'PRONTUARIO PRIVADO', 'MATRICULA PRIVADA', '1970-01-01', 'prescricao'):
            self.assertNotIn(valor, r.text)
        for headers in ({'If-None-Match': r.headers['etag']}, {'Authorization': 'Bearer expirado', 'If-None-Match': r.headers['etag']}):
            igual = await self.cliente.get(self.base + '/estado', headers=headers)
            self.assertEqual(igual.status_code, 304)
            self.assertFalse(igual.content)
        restrito = await self.cliente.get(f'/api/operacao/unidades/{self.a}/estado')
        self.assertNotIn('Paciente fictício', restrito.text)
        self.assertNotEqual(restrito.headers['etag'], r.headers['etag'])

    async def test_fluxo_completo_sem_login_e_sem_pular_etapa(self):
        rota = self.rota('PENDENTE')
        self.assertEqual((await self.cliente.patch(rota, json={'status': 'PRONTO'})).status_code, 409)
        for etapa in ('EM_PREPARO', 'PRONTO'):
            r = await self.cliente.patch(rota, json={'status': etapa}, headers={'Authorization': 'Bearer expirado'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['status'], etapa)
            self.assertIn('Paciente fictício', r.text)
        self.assertEqual((await self.cliente.patch(rota, json={'status': 'ENTREGUE'})).status_code, 422)
        async with self.sessoes() as db:
            pedido = await db.get(Pedido, self.ids['PENDENTE'])
            self.assertIsNotNone(pedido.concluido_em)
            historico = (await db.scalars(select(HistoricoPedido))).all()
            self.assertEqual(len(historico), 2)
            self.assertTrue(all(h.alterado_por_usuario_id is None for h in historico))
            eventos = (await db.scalars(select(EventoAssistencial))).all()
            self.assertTrue(all(e.autor_nome == 'Painel da cozinha (sem login)' and e.autor_usuario_id is None for e in eventos))
        for etapa in ('ENTREGUE', 'CANCELADO'):
            self.assertEqual((await self.cliente.patch(self.rota(etapa), json={'status': 'EM_PREPARO'})).status_code, 409)

    async def test_cancelamento_exige_motivo_e_relatorio_identifica_painel_sem_inventar_usuario(self):
        rota = self.rota('PENDENTE')
        for motivo in (None, '', '   ', 'abcd'):
            self.assertEqual((await self.cliente.patch(rota, json={'status': 'CANCELADO', 'motivo': motivo})).status_code, 422)
        r = await self.cliente.patch(rota, json={'status': 'CANCELADO', 'motivo': '  Pedido duplicado  ', 'usuario_id': 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.cliente.patch(rota, json={'status': 'CANCELADO', 'motivo': 'Outro motivo'})).status_code, 409)
        async with self.sessoes() as db:
            evento = await db.scalar(select(EventoAssistencial).where(EventoAssistencial.pedido_id == self.ids['PENDENTE']))
            self.assertEqual(evento.autor_nome, 'Painel da cozinha (sem login)')
            self.assertEqual(evento.autor_perfil, 'COZINHA_PUBLICA')
            self.assertIsNone(evento.autor_usuario_id)
            self.assertEqual(evento.motivo, 'Pedido duplicado')
            self.assertIsNotNone(evento.criado_em)
        relatorio = await self.cliente.get('/api/relatorios/dietas-periodo', headers=self.admin,
            params={'inicio': '2020-01-01T00:00:00Z', 'fim': '2100-01-01T00:00:00Z'})
        self.assertEqual(relatorio.status_code, 200, relatorio.text)
        item = next(i for i in relatorio.json()['itens'] if i['pedido_id'] == self.ids['PENDENTE'])
        self.assertEqual(item['solicitante_nome'], 'Solicitante fictício')
        self.assertEqual(item['cancelado_por_nome'], 'Painel da cozinha (sem login)')
        self.assertIsNone(item['cancelado_por_usuario_id'])
        self.assertEqual(item['motivo_cancelamento'], 'Pedido duplicado')

    async def test_filipeta_e_etiqueta_sem_login_respeitam_pronto_e_conferencia_de_envio_incerto(self):
        with patch('app.services.fila_impressao.enviar_filipeta') as transporte:
            r = await self.cliente.post(self.rota('PENDENTE', 'reimprimir'), json={})
            self.assertEqual(r.status_code, 202, r.text)
            job_id = r.json()['impressao']['id']
            async with self.sessoes() as db:
                job = await db.get(TrabalhoImpressao, job_id)
                self.assertIsNone(job.solicitado_por_usuario_id)
                job.estado = 'INCERTO'; await db.commit()
            self.assertEqual((await self.cliente.post(self.rota('PENDENTE', 'reimprimir'), json={})).status_code, 409)
            self.assertEqual((await self.cliente.post(self.rota('PENDENTE', 'reimprimir'), json={'confirmar_risco_duplicidade': True})).status_code, 202)
            for metodo in (self.cliente.get, self.cliente.post):
                self.assertEqual((await metodo(self.rota('PENDENTE', 'etiqueta'))).status_code, 409)
            previa = await self.cliente.get(self.rota('PRONTO', 'etiqueta'))
            self.assertEqual(previa.status_code, 200)
            self.assertTrue(previa.content.startswith(b'\x89PNG'))
            for _ in range(2):
                self.assertEqual((await self.cliente.post(self.rota('PRONTO', 'etiqueta'), json={})).status_code, 202)
            async with self.sessoes() as db:
                self.assertEqual(await db.scalar(select(func.count()).select_from(TrabalhoImpressao).where(TrabalhoImpressao.tipo_documento == 'ETIQUETA')), 1)
            transporte.assert_not_called()

    async def test_unidade_do_pedido_e_ativa_sao_validadas_e_entrega_gestao_continuam_protegidas(self):
        outro = f'/api/cozinha/unidades/{self.b}/pedidos/{self.ids["PENDENTE"]}'
        self.assertEqual((await self.cliente.patch(outro + '/status', json={'status': 'EM_PREPARO'})).status_code, 404)
        self.assertEqual((await self.cliente.post(outro + '/reimprimir')).status_code, 404)
        for url in ('/api/admin/usuarios', '/api/gestao/dietas?filial_id=1', f'/api/relatorios/entregas?filial_id={self.a}'):
            self.assertEqual((await self.cliente.get(url)).status_code, 401)
        entregar = f'/api/operacao/unidades/{self.a}/pedidos/{self.ids["PRONTO"]}/entregar'
        self.assertEqual((await self.cliente.post(entregar, json={})).status_code, 401)
        self.assertEqual((await self.cliente.post(self.rota('PRONTO', 'entregar'), json={})).status_code, 404)
        async with self.sessoes() as db:
            (await db.get(Filial, self.a)).ativa = False; await db.commit()
        self.assertEqual((await self.cliente.get(self.base + '/estado')).status_code, 404)
        self.assertEqual((await self.cliente.patch(self.rota('PENDENTE'), json={'status': 'EM_PREPARO'})).status_code, 404)

    async def test_websocket_e_contexto_da_cozinha_sem_login_mantem_isolamento(self):
        canais = ConnectionManager()
        cozinha, publico = Socket(), Socket()
        await canais.conectar_cozinha(self.a, cozinha)
        await canais.conectar_publico(self.a, publico)
        async with self.sessoes() as db:
            pedido = await db.scalar(select(Pedido).options(selectinload(Pedido.dieta)).where(Pedido.id == self.ids['PENDENTE']))
        from app.schemas.schemas import PedidoOut
        await canais.transmitir(self.a, {'evento': 'status_alterado', 'pedido': PedidoOut.model_validate(pedido).model_dump(mode='json')})
        self.assertIn('nome_paciente', cozinha.mensagens[0]['pedido'])
        self.assertNotIn('nome_paciente', publico.mensagens[0]['pedido'])
        self.assertNotIn('matricula', cozinha.mensagens[0]['pedido']['dados_dinamicos'])
        await MonitorContexto().atualizar(self.sessoes, canais)
        self.assertIn('alertas', cozinha.mensagens[-1])
        self.assertNotIn('copeiras', cozinha.mensagens[-1])
        await canais.encerrar_usuario(1)
        self.assertIsNone(cozinha.fechado)
        with patch('app.main.SessionLocal', self.sessoes), patch('app.main.gerenciador_ws', canais):
            socket = Socket(); await ws_cozinha_publica(socket, self.a)
            self.assertTrue(socket.aceito)
            self.assertEqual(socket.mensagens, [{'evento': 'pong'}])
        async with self.sessoes() as db:
            (await db.get(Filial, self.a)).ativa = False; await db.commit()
        await MonitorContexto().atualizar(self.sessoes, canais)
        self.assertEqual(cozinha.fechado, 1008)
        with patch('app.main.SessionLocal', self.sessoes):
            recusado = Socket(); await ws_cozinha_publica(recusado, self.a)
            self.assertEqual(recusado.fechado, 1008)


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_POSTGRES_URL'), 'Requer PostgreSQL de teste')
class CozinhaSemLoginPostgresTest(CozinhaSemLoginTest):
    async def criar_engine(self):
        url = os.environ['CNUTRI_TEST_POSTGRES_URL']
        self.schema = 'teste_cozinha_' + uuid4().hex
        self.admin_engine = create_async_engine(url)
        async with self.admin_engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        return create_async_engine(url, connect_args={'server_settings': {'search_path': self.schema}})

    async def test_dois_cancelamentos_simultaneos_preservam_uma_unica_evidencia(self):
        respostas = await asyncio.gather(*[self.cliente.patch(self.rota('PENDENTE'), json={'status': 'CANCELADO', 'motivo': m})
            for m in ('Pedido em duplicidade', 'Cancelado por solicitação')])
        self.assertEqual(sorted(r.status_code for r in respostas), [200, 409])
        async with self.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(EventoAssistencial)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido)), 1)
