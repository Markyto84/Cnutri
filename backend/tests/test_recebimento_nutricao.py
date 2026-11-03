"""Comprovação em banco descartável, sem envio a impressoras nem dados reais."""
import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from sqlalchemy import func, inspect, select

import test_cozinha_sem_login as fixtures
from app.core.config import settings
from app.core.sessoes import emitir_sessao
from app.models.models import ComprovanteEntrega, EventoAssistencial, Filial, HistoricoPedido, Pedido, Perfil, RecebimentoQR, RetiradaPedido, Usuario
from app.services.foto_comprovante import MAX_FOTO_BYTES, MAX_UPLOAD_BYTES, otimizar_foto
from app.services.impressora import compor_linhas_filipeta
from app.services.impressao_raster import renderizar_filipeta
from app.services.recebimento_qr import endereco_recebimento, preparar_codigo
from fastapi import HTTPException


def foto_ficticia():
    imagem = Image.new('RGB', (1000, 1800), 'white')
    desenho = ImageDraw.Draw(imagem)
    for y in range(40, 1700, 45):
        desenho.text((40, y), 'COMPROVANTE FICTICIO - NOME, ASSINATURA, DATA E HORA', fill='black')
    saida = BytesIO()
    imagem.save(saida, format='PNG')
    return saida.getvalue()


class FotoComprovanteTest(unittest.TestCase):
    def test_limita_resolucao_remove_exif_e_guarda_jpeg_binario_compacto(self):
        imagem = Image.new('RGB', (3000, 4000), 'white')
        desenho = ImageDraw.Draw(imagem)
        for y in range(80, 3900, 75):
            desenho.text((100, y), 'COMPROVANTE FICTICIO 03/11/2026 12:30 NOME ASSINATURA', fill='black', font_size=40)
        exif = Image.Exif(); exif[270] = 'METADADO PRIVADO'; exif[274] = 6
        original = BytesIO(); imagem.save(original, format='JPEG', quality=98, exif=exif)
        foto = otimizar_foto(original.getvalue())
        self.assertLessEqual(len(foto.dados), MAX_FOTO_BYTES)
        self.assertLessEqual(max(foto.largura, foto.altura), 2000)
        self.assertGreater(foto.largura, foto.altura)  # orientação EXIF aplicada
        with Image.open(BytesIO(foto.dados)) as final:
            self.assertEqual(final.format, 'JPEG')
            self.assertEqual(final.mode, 'L')
            self.assertFalse(final.getexif())
            self.assertEqual(final.getextrema(), (0, 255))
        self.assertEqual(len(foto.sha256), 64)

    def test_rejeita_arquivo_invalido_svg_pequeno_animado_e_excessivo(self):
        pequeno = BytesIO(); Image.new('RGB', (100, 100)).save(pequeno, format='PNG')
        animado = BytesIO(); Image.new('RGB', (800, 1000)).save(animado, format='WEBP', save_all=True, append_images=[Image.new('RGB', (800, 1000), 'white')], duration=100)
        for dados in (b'', b'<svg/>', pequeno.getvalue(), animado.getvalue(), b'x' * (MAX_UPLOAD_BYTES + 1)):
            with self.subTest(tamanho=len(dados)), self.assertRaises(HTTPException):
                otimizar_foto(dados)


class RecebimentoNutricaoTest(unittest.IsolatedAsyncioTestCase):
    fixture = fixtures.CozinhaSemLoginTest

    async def asyncSetUp(self):
        self.f = self.fixture('test_fluxo_completo_sem_login_e_sem_pular_etapa')
        await self.f.asyncSetUp()
        self.config = patch.object(settings, 'URL_RECEBIMENTO_PUBLICA', 'https://cnutri.test')
        self.config.start()
        self.foto = foto_ficticia()
        self.horario = (datetime.now(timezone.utc) - timedelta(minutes=30)).replace(second=0, microsecond=0)
        self.tokens = {'ADMIN_TI': self.f.admin}
        async with self.f.sessoes() as db:
            for perfil, filial in [('NUTRICIONISTA', self.f.a), ('OUTRA_UNIDADE', self.f.b), ('COPEIRA', self.f.a), ('COZINHA', self.f.a)]:
                nome_perfil = 'NUTRICIONISTA' if perfil == 'OUTRA_UNIDADE' else perfil
                model_perfil = await db.scalar(select(Perfil).where(Perfil.nome == nome_perfil))
                if model_perfil is None:
                    model_perfil = Perfil(nome=nome_perfil); db.add(model_perfil)
                usuario = Usuario(nome=f'Conta fictícia {perfil}', nome_usuario=perfil.lower(), senha_hash='NAO-UTILIZADO',
                    perfil=model_perfil, filiais=[await db.get(Filial, filial)])
                db.add(usuario); await db.flush()
                self.tokens[perfil] = {'Authorization': 'Bearer ' + (await emitir_sessao(db, usuario, filial)).access_token}
            await db.commit()

    async def asyncTearDown(self):
        self.config.stop()
        await self.f.asyncTearDown()

    async def criar(self, status='PRONTO'):
        async with self.f.sessoes() as db:
            pedido = Pedido(filial_id=self.f.a, tipo_solicitacao='PACIENTE', status=status,
                criado_em=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
                solicitante_nome='Solicitante fictício', solicitante_identificacao='REGISTRO PRIVADO',
                nome_paciente='Paciente fictício privado', dados_dinamicos={'refeicao':'ALMOÇO'})
            db.add(pedido); await db.flush()
            codigo = await preparar_codigo(db, pedido)
            await db.commit()
            return pedido.id, codigo.codigo

    async def confirmar(self, codigo, perfil='NUTRICIONISTA', nome='João da Conceição', horario=None, foto=None):
        return await self.f.cliente.post('/api/recebimentos/confirmar', headers=self.tokens.get(perfil, {}),
            data={'codigo':codigo, 'recebedor_nome':nome, 'entregue_em':horario or self.horario.isoformat()},
            files={'foto':('filipeta.jpg', foto if foto is not None else self.foto, 'image/jpeg')})

    async def test_nutricao_salva_horario_manual_foto_e_autoria_sem_copeira(self):
        pedido, codigo = await self.criar()
        primeira = await self.confirmar(codigo)
        self.assertEqual(primeira.status_code, 200, primeira.text)
        resumo = primeira.json()
        self.assertEqual(resumo['status'], 'ENTREGUE')
        self.assertEqual(datetime.fromisoformat(resumo['entregue_em']), self.horario)
        self.assertGreater(datetime.fromisoformat(resumo['registrado_em']), self.horario)
        self.assertEqual(resumo['recebedor_nome'], 'João da Conceição')
        self.assertTrue(resumo['comprovante_disponivel'])
        async with self.f.sessoes() as db:
            prova = await db.get(ComprovanteEntrega, pedido)
            self.assertIn('foto_jpeg', inspect(prova).unloaded)
            self.assertLessEqual(prova.foto_bytes, MAX_FOTO_BYTES)
            self.assertEqual(await db.scalar(select(func.count()).select_from(RetiradaPedido)), 0)
            evento = await db.scalar(select(EventoAssistencial).where(EventoAssistencial.pedido_id == pedido))
            self.assertEqual(evento.acao, 'ENTREGA_COMPROVADA_NUTRICAO')
            self.assertEqual(evento.autor_nome, 'Conta fictícia NUTRICIONISTA')
            self.assertEqual(evento.depois['foto_sha256'], prova.foto_sha256)
        outra = await self.confirmar(codigo, nome='Outra Pessoa')
        self.assertEqual(outra.json(), resumo)  # repetição não sobrescreve o comprovante
        async with self.f.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ComprovanteEntrega)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido).where(HistoricoPedido.pedido_id == pedido)), 1)

    async def test_apenas_nutricao_e_ti_da_unidade_podem_lancar_e_ver_foto(self):
        pedido, codigo = await self.criar()
        for perfil, status in [('SEM_SESSAO',401),('COPEIRA',403),('COZINHA',403),('OUTRA_UNIDADE',403)]:
            resposta = await self.confirmar(codigo, perfil=perfil)
            self.assertEqual(resposta.status_code,status,resposta.text)
        self.assertEqual((await self.confirmar(codigo, perfil='ADMIN_TI')).status_code,200)
        caminho = f'/api/relatorios/entregas/{pedido}/comprovante'
        for perfil, status in [('SEM_SESSAO',401),('COPEIRA',403),('COZINHA',403),('OUTRA_UNIDADE',403),('ADMIN_TI',200),('NUTRICIONISTA',200)]:
            foto = await self.f.cliente.get(caminho, params={'filial_id':self.f.a}, headers=self.tokens.get(perfil,{}))
            self.assertEqual(foto.status_code,status,foto.text if status != 200 else '')
            if status == 200:
                self.assertEqual(foto.headers['content-type'],'image/jpeg')
                self.assertIn('no-store',foto.headers['cache-control'])
                self.assertLessEqual(len(foto.content),MAX_FOTO_BYTES)
        errado = await self.f.cliente.get(caminho, params={'filial_id':self.f.b}, headers=self.f.admin)
        self.assertEqual(errado.status_code,404)

    async def test_consulta_publica_nao_expoe_nome_paciente_recebedor_ou_foto(self):
        pedido, codigo = await self.criar()
        await self.confirmar(codigo)
        publico = await self.f.cliente.post('/api/recebimentos/consultar', json={'codigo':codigo})
        self.assertEqual(publico.status_code,200)
        self.assertNotIn('João',publico.text)
        self.assertNotIn('Paciente',publico.text)
        self.assertNotIn('foto_jpeg',publico.text)
        privado = await self.f.cliente.post('/api/recebimentos/detalhes', json={'codigo':codigo},headers=self.tokens['NUTRICIONISTA'])
        self.assertIn('Paciente fictício privado',privado.text)

    async def test_dados_e_foto_obrigatorios_nao_podem_finalizar_parcialmente(self):
        pedido, codigo = await self.criar()
        for nome in ('', '12345', '=João', 'João\nSilva'):
            resposta = await self.confirmar(codigo,nome=nome)
            self.assertEqual(resposta.status_code,422,resposta.text)
        for horario in ('2020-01-01T12:00:00-03:00', '2099-01-01T12:00:00-03:00', '2026-11-03T12:00:00'):
            resposta = await self.confirmar(codigo,horario=horario)
            self.assertEqual(resposta.status_code,422,resposta.text)
        self.assertEqual((await self.confirmar(codigo,foto=b'<svg/>')).status_code,422)
        sem_foto = await self.f.cliente.post('/api/recebimentos/confirmar',headers=self.tokens['NUTRICIONISTA'],data={'codigo':codigo,'recebedor_nome':'Pessoa Teste','entregue_em':self.horario.isoformat()})
        self.assertEqual(sem_foto.status_code,422)
        async with self.f.sessoes() as db:
            self.assertEqual((await db.get(Pedido,pedido)).status,'PRONTO')
            self.assertIsNone((await db.get(RecebimentoQR,pedido)).confirmado_em)
            self.assertIsNone(await db.get(ComprovanteEntrega,pedido))

    async def test_so_pronto_pode_finalizar_e_codigo_corrigido_nao_funciona(self):
        for status in ('PENDENTE','EM_PREPARO','CANCELADO'):
            pedido,codigo = await self.criar(status)
            self.assertEqual((await self.confirmar(codigo)).status_code,409)
        pedido,codigo = await self.criar()
        async with self.f.sessoes() as db:
            atual = await db.get(Pedido,pedido); atual.versao=2
            await preparar_codigo(db,atual); await db.commit()
        self.assertEqual((await self.confirmar(codigo)).status_code,404)
        self.assertEqual((await self.confirmar('x'*43)).status_code,404)

    async def test_relatorios_e_exportacoes_usam_data_da_filipeta_e_disponibilizam_foto(self):
        pedido,codigo=await self.criar()
        await self.confirmar(codigo)
        relatorio=await self.f.cliente.get('/api/relatorios/entregas',params={'filial_id':self.f.a},headers=self.f.admin)
        self.assertEqual(relatorio.status_code,200,relatorio.text)
        item=next(i for i in relatorio.json()['itens'] if i['pedido_id']==pedido)
        self.assertEqual(item['origem_entrega'],'Nutrição · filipeta assinada')
        self.assertTrue(item['comprovante_disponivel'])
        self.assertEqual(item['registrado_por_nome'],'Conta fictícia NUTRICIONISTA')
        self.assertIsNone(item['copeira_nome'])
        self.assertEqual(datetime.fromisoformat(item['entregue_em']),self.horario)
        rastreio=await self.f.cliente.get(f'/api/assistencia/pedidos/{pedido}',headers=self.f.admin)
        self.assertEqual(rastreio.status_code,200,rastreio.text)
        self.assertEqual(datetime.fromisoformat(rastreio.json()['entrega']['entregue_em']),self.horario)
        self.assertTrue(rastreio.json()['entrega']['comprovante_disponivel'])
        self.assertEqual(rastreio.json()['entrega']['origem_entrega'],'Nutrição · filipeta assinada')
        params={'inicio':(self.horario-timedelta(minutes=1)).isoformat(),'fim':(self.horario+timedelta(minutes=1)).isoformat(),'data_base':'entrega','filial_id':self.f.a}
        tela=await self.f.cliente.get('/api/relatorios/dietas-periodo',params=params,headers=self.f.admin)
        self.assertEqual(tela.status_code,200,tela.text)
        self.assertEqual([i['pedido_id'] for i in tela.json()['itens']],[pedido])
        for formato in ('csv','xlsx','ods'):
            arquivo=await self.f.cliente.get('/api/relatorios/dietas-periodo/exportar',params={**params,'formato':formato},headers=self.f.admin)
            self.assertEqual(arquivo.status_code,200,arquivo.text if formato=='csv' else '')
            if formato=='csv':
                self.assertIn('Foto da filipeta disponível',arquivo.text)
                self.assertIn('Conta fictícia NUTRICIONISTA',arquivo.text)

    async def test_falha_na_gravacao_reverte_status_e_comprovante(self):
        pedido,codigo=await self.criar()
        with patch('app.services.recebimento_qr.registrar_evento',side_effect=RuntimeError('Falha fictícia')):
            with self.assertRaisesRegex(RuntimeError,'Falha fictícia'):
                await self.confirmar(codigo)
        async with self.f.sessoes() as db:
            self.assertEqual((await db.get(Pedido,pedido)).status,'PRONTO')
            self.assertIsNone((await db.get(RecebimentoQR,pedido)).confirmado_em)
            self.assertIsNone(await db.get(ComprovanteEntrega,pedido))

    async def test_rotas_das_copeiras_nao_finalizam_e_historico_anterior_e_preservado(self):
        pedido,codigo=await self.criar()
        for acao in ('retirar','entregar'):
            rota=f'/api/operacao/unidades/{self.f.a}/pedidos/{pedido}/{acao}'
            resposta=await self.f.cliente.post(rota,headers=self.f.admin,json={})
            self.assertEqual(resposta.status_code,410,resposta.text)
        antiga=await self.f.cliente.post('/api/recebimentos/identificar',json={'codigo':codigo},headers=self.tokens['COPEIRA'])
        self.assertEqual(antiga.status_code,403)
        async with self.f.sessoes() as db:
            qr=await db.get(RecebimentoQR,pedido)
            qr.confirmado_em=datetime(2026,10,1,12)
            qr.registro_profissional='COREN 123'; qr.recebedor_nome='Nome histórico'
            (await db.get(Pedido,pedido)).status='ENTREGUE'; await db.commit()
        repetida=await self.confirmar(codigo)
        self.assertEqual(repetida.status_code,200,repetida.text)
        async with self.f.sessoes() as db:
            qr=await db.get(RecebimentoQR,pedido)
            self.assertEqual(qr.registro_profissional,'COREN 123')
            self.assertEqual(qr.recebedor_nome,'Nome histórico')
            self.assertIsNone(await db.get(ComprovanteEntrega,pedido))

    async def test_filipeta_preserva_campos_manualmente_e_qr_fica_so_no_cabecalho(self):
        pedido,codigo=await self.criar()
        async with self.f.sessoes() as db:
            linhas=compor_linhas_filipeta(await db.get(Pedido,pedido),'Unidade de teste',url_recebimento=endereco_recebimento(await db.get(RecebimentoQR,pedido)))
        self.assertTrue(linhas[0].cabecalho_qr)
        self.assertEqual(sum(bool(l.url_qr) for l in linhas),1)
        textos='\n'.join(l.texto for l in linhas)
        for esperado in ('Recebedor:','Assinatura:','Data e hora:','ALMOÇO'):
            self.assertIn(esperado,textos)
        self.assertNotIn('Informe nome e registro profissional',textos)
        imagem=renderizar_filipeta(linhas)
        self.assertEqual(imagem.width,576)
        self.assertIsNotNone(imagem.crop((350,8,552,200)).getbbox())


@unittest.skipUnless(os.environ.get('CNUTRI_TEST_POSTGRES_URL'),'Requer PostgreSQL de teste')
class RecebimentoNutricaoPostgresTest(RecebimentoNutricaoTest):
    fixture=fixtures.CozinhaSemLoginPostgresTest

    async def test_duas_confirmacoes_concorrentes_preservam_um_comprovante(self):
        pedido,codigo=await self.criar()
        respostas=await asyncio.gather(self.confirmar(codigo,nome='Primeira Pessoa'),self.confirmar(codigo,nome='Segunda Pessoa'))
        self.assertEqual([r.status_code for r in respostas],[200,200],[r.text for r in respostas])
        self.assertEqual(respostas[0].json(),respostas[1].json())
        async with self.f.sessoes() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ComprovanteEntrega)),1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(HistoricoPedido).where(HistoricoPedido.pedido_id==pedido)),1)

    async def test_cancelamento_concorrente_nao_deixa_cancelado_com_comprovante(self):
        pedido,codigo=await self.criar()
        entrega,cancelamento=await asyncio.gather(self.confirmar(codigo),self.f.cliente.patch(f'{self.f.base}/pedidos/{pedido}/status',json={'status':'CANCELADO','motivo':'Teste concorrente'}))
        self.assertEqual(sorted([entrega.status_code,cancelamento.status_code]),[200,409])
        async with self.f.sessoes() as db:
            self.assertEqual((await db.get(Pedido,pedido)).status=='ENTREGUE',(await db.get(ComprovanteEntrega,pedido)) is not None)
