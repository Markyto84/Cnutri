"""Código opaco da filipeta e confirmação única, sem autenticação pessoal do navegador."""
import re
import secrets
import unicodedata

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update

from ..core.config import settings
from ..core.ws import gerenciador_ws
from ..models.models import Filial, HistoricoPedido, Pedido, RecebimentoQR
from ..schemas.schemas import PedidoOut
from .assistencia import registrar_evento
from .operacao import data_utc


class ConsultaRecebimento(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codigo: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]{43}$')


class ConfirmacaoRecebimento(ConsultaRecebimento):
    registro_profissional: str = Field(min_length=3, max_length=50)

    @field_validator('registro_profissional')
    @classmethod
    def validar_registro(cls, valor):
        valor = unicodedata.normalize('NFKC', valor).strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9 ./-]{2,49}', valor) or not any(c.isdigit() for c in valor):
            raise ValueError('Informe o registro profissional, por exemplo COREN-SP 123456')
        return valor


async def preparar_codigo(db, pedido):
    if not settings.URL_RECEBIMENTO_PUBLICA:
        return None
    codigo = await db.get(RecebimentoQR, pedido.id)
    if codigo is None:
        codigo = RecebimentoQR(pedido_id=pedido.id, versao=pedido.versao or 1,
            codigo=secrets.token_urlsafe(32), url_base=settings.URL_RECEBIMENTO_PUBLICA)
        db.add(codigo)
    elif codigo.versao != pedido.versao:
        if codigo.confirmado_em is not None:
            raise HTTPException(409, 'O recebimento já foi confirmado')
        codigo.codigo, codigo.versao = secrets.token_urlsafe(32), pedido.versao
    codigo.url_base = settings.URL_RECEBIMENTO_PUBLICA
    await db.flush()
    return codigo


def endereco_recebimento(codigo):
    # O fragmento não é enviado no pedido HTTP nem no cabeçalho Referer.
    return f'{codigo.url_base}/receber#{codigo.codigo}'


async def consultar_codigo(db, valor, bloquear=False):
    codigo = await db.scalar(select(RecebimentoQR).where(RecebimentoQR.codigo == valor))
    if codigo is None:
        raise HTTPException(404, 'QR Code inválido ou substituído. Confira a filipeta com a cozinha')
    consulta = select(Pedido).where(Pedido.id == codigo.pedido_id)
    if bloquear:
        consulta = consulta.with_for_update(of=Pedido)
    pedido = await db.scalar(consulta)
    if bloquear:
        await db.refresh(codigo)
    filial = await db.get(Filial, pedido.filial_id)
    if not filial or not filial.ativa or codigo.codigo != valor or codigo.versao != pedido.versao:
        raise HTTPException(404, 'QR Code indisponível. Confira a filipeta com a cozinha')
    return codigo, pedido, filial


def resumo_recebimento(codigo, pedido, filial):
    return {'pedido_id': pedido.id, 'unidade': filial.nome, 'status': pedido.status,
        'pode_confirmar': pedido.status == 'PRONTO', 'confirmado_em': data_utc(codigo.confirmado_em)}


async def confirmar_recebimento(db, dados, ip):
    codigo, pedido, filial = await consultar_codigo(db, dados.codigo, bloquear=True)
    if codigo.confirmado_em is not None:
        return resumo_recebimento(codigo, pedido, filial)
    if pedido.status != 'PRONTO':
        raise HTTPException(409, 'O recebimento só pode ser confirmado para uma refeição pronta e não cancelada')
    alterado = await db.scalar(update(Pedido).where(Pedido.id == pedido.id, Pedido.status == 'PRONTO')
        .values(status='ENTREGUE').returning(Pedido.id).execution_options(synchronize_session=False))
    if alterado is None:
        raise HTTPException(409, 'A refeição já foi atualizada. Consulte novamente a filipeta')
    codigo.registro_profissional = dados.registro_profissional
    codigo.confirmado_em, codigo.ip_origem = func.now(), ip
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior='PRONTO', status_novo='ENTREGUE', alterado_por_usuario_id=None))
    registrar_evento(db, pedido, 'ENTREGA_CONFIRMADA_QR', depois={'status': 'ENTREGUE',
        'registro_profissional': dados.registro_profissional}, origem='RECEBEDOR_QR')
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=['dieta', 'trabalhos_impressao'])
    await db.refresh(codigo)
    await gerenciador_ws.transmitir(pedido.filial_id, {'evento': 'status_alterado',
        'pedido': PedidoOut.model_validate(pedido).model_dump(mode='json')})
    return resumo_recebimento(codigo, pedido, filial)
