"""Compatibilidade do painel desativado e preservação dos recebimentos antigos."""
from datetime import datetime
import unittest

from sqlalchemy import func, select
import test_entregas as fixtures
from app.models.models import Pedido, RecebimentoQR, RetiradaPedido


class RetiradaDesativadaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.f = fixtures.EntregasTest('test_dashboard_abre_sem_login_e_publica_apenas_dados_operacionais')
        await self.f.asyncSetUp()

    async def asyncTearDown(self):
        await self.f.asyncTearDown()

    async def test_nenhuma_conta_consegue_finalizar_pelo_painel_antigo(self):
        copeira = await self.f.entrar()
        pedido = self.f.pedidos['PRONTO']
        for acao in ('retirar', 'entregar'):
            rota = f'{self.f.base}/pedidos/{pedido}/{acao}'
            self.assertEqual((await self.f.client.post(rota,json={})).status_code,401)
            for token in (copeira,self.f.operador):
                resposta = await self.f.client.post(rota,headers=token,json={'copeira_id':self.f.ana})
                self.assertEqual(resposta.status_code,410,resposta.text)
        async with self.f.sessoes() as db:
            self.assertEqual((await db.get(Pedido,pedido)).status,'PRONTO')
            self.assertEqual(await db.scalar(select(func.count()).select_from(RetiradaPedido)),0)

    async def test_desativacao_preserva_copeira_e_qr_historicos_no_relatorio(self):
        pedido = self.f.pedidos['PRONTO']
        async with self.f.sessoes() as db:
            (await db.get(Pedido,pedido)).status='ENTREGUE'
            db.add(RecebimentoQR(pedido_id=pedido,codigo='a'*43,versao=1,url_base='https://teste.invalid',
                recebedor_nome='Recebedor histórico',registro_profissional='COREN 123',confirmado_em=datetime(2026,10,20,15)))
            db.add(RetiradaPedido(pedido_id=pedido,versao=1,copeira_id=self.f.ana,copeira_nome='Ana Teste',
                registrado_por_usuario_id=self.f.ana,retirada_em=datetime(2026,10,20,14,30)))
            await db.commit()
        resposta = await self.f.client.get('/api/relatorios/entregas',params={'filial_id':self.f.a},headers=self.f.operador)
        self.assertEqual(resposta.status_code,200,resposta.text)
        item = resposta.json()['itens'][0]
        self.assertEqual(item['copeira_nome'],'Ana Teste')
        self.assertEqual(item['recebedor_nome'],'Recebedor histórico')
        self.assertEqual(item['recebedor_registro_profissional'],'COREN 123')
        self.assertEqual(item['origem_entrega'],'QR Code')
        self.assertFalse(item['comprovante_disponivel'])
        self.assertIsNotNone(item['retirada_em'])