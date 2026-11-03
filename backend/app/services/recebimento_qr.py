"""Filipeta assinada em papel e comprovação manual autenticada pela Nutrição."""
import secrets
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update

from ..core.config import settings
from ..core.security import verificar_acesso_filial
from ..core.ws import gerenciador_ws
from ..models.models import ComprovanteEntrega, Filial, HistoricoPedido, Pedido, RecebimentoQR
from ..schemas.schemas import PedidoOut
from .assistencia import registrar_evento
from .operacao import data_utc


class ConsultaRecebimento(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codigo: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]{43}$')


class ConfirmacaoRecebimento(ConsultaRecebimento):
    recebedor_nome: str = Field(min_length=3, max_length=120)
    entregue_em: datetime

    @field_validator('recebedor_nome')
    @classmethod
    def validar_nome(cls, valor):
        valor = ' '.join(p for p in unicodedata.normalize('NFKC', valor).strip().split(' ') if p)
        if (not 3 <= len(valor) <= 120 or not valor[0].isalpha() or sum(c.isalpha() for c in valor) < 2
            or not all(c.isalpha() or unicodedata.category(c).startswith('M') or c in " '’.-" for c in valor)):
            raise ValueError('Informe o nome completo do recebedor')
        return valor

    @field_validator('entregue_em')
    @classmethod
    def validar_horario(cls, valor):
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError('Informe a data e hora da entrega com fuso horário')
        return valor.astimezone(timezone.utc).replace(tzinfo=None)


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
        consulta = consulta.with_for_update(of=Pedido).execution_options(populate_existing=True)
    pedido = await db.scalar(consulta)
    if bloquear:
        await db.refresh(codigo)
    filial = await db.get(Filial, pedido.filial_id)
    if not filial or not filial.ativa or codigo.codigo != valor or codigo.versao != pedido.versao:
        raise HTTPException(404, 'QR Code indisponível. Confira a filipeta com a cozinha')
    return codigo, pedido, filial


def resumo_recebimento(codigo, pedido, filial, comprovante=None, privado=False):
    resumo = {'pedido_id': pedido.id, 'filial_id': filial.id, 'unidade': filial.nome, 'status': pedido.status,
        'pode_confirmar': pedido.status == 'PRONTO' and codigo.confirmado_em is None,
        'confirmado_em': data_utc(codigo.confirmado_em),
        'entregue_em': data_utc(comprovante.entregue_em if comprovante else codigo.confirmado_em),
        'registrado_em': data_utc(comprovante.registrado_em) if comprovante else None,
        'comprovante_disponivel': comprovante is not None}
    if privado:
        resumo.update(recebedor_nome=codigo.recebedor_nome,
            destinatario=pedido.nome_paciente or pedido.solicitante_nome,
            leito=pedido.leito, refeicao=(pedido.dados_dinamicos or {}).get('refeicao'),
            registrado_por_nome=comprovante.registrado_por_nome if comprovante else None,
            criado_em=data_utc(pedido.criado_em))
    return resumo


async def confirmar_recebimento(db, dados, foto, ip, usuario):
    codigo, pedido, filial = await consultar_codigo(db, dados.codigo, bloquear=True)
    await verificar_acesso_filial(filial.id, usuario, db)
    if codigo.confirmado_em is not None:
        comprovante = await db.get(ComprovanteEntrega, pedido.id)
        return resumo_recebimento(codigo, pedido, filial, comprovante, privado=True)
    if pedido.status != 'PRONTO':
        raise HTTPException(409, 'O recebimento só pode ser confirmado para uma refeição pronta e não cancelada')
    if dados.entregue_em > datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(422, 'A data e hora da entrega não podem estar no futuro')
    if dados.entregue_em < pedido.criado_em.replace(tzinfo=None, second=0, microsecond=0):
        raise HTTPException(422, 'A entrega não pode ser anterior à solicitação da refeição')
    alterado = await db.scalar(update(Pedido).where(Pedido.id == pedido.id, Pedido.status == 'PRONTO')
        .values(status='ENTREGUE').returning(Pedido.id).execution_options(synchronize_session=False))
    if alterado is None:
        raise HTTPException(409, 'A refeição já foi atualizada. Consulte novamente a filipeta')
    codigo.recebedor_nome, codigo.registro_profissional = dados.recebedor_nome, None
    codigo.confirmado_em, codigo.ip_origem = func.now(), ip
    comprovante = ComprovanteEntrega(pedido_id=pedido.id, entregue_em=dados.entregue_em,
        registrado_por_usuario_id=usuario.id, registrado_por_nome=usuario.nome,
        foto_jpeg=foto.dados, foto_sha256=foto.sha256, foto_bytes=len(foto.dados),
        foto_largura=foto.largura, foto_altura=foto.altura)
    db.add(comprovante)
    db.add(HistoricoPedido(pedido_id=pedido.id, status_anterior='PRONTO', status_novo='ENTREGUE', alterado_por_usuario_id=usuario.id))
    registrar_evento(db, pedido, 'ENTREGA_COMPROVADA_NUTRICAO', usuario, depois={'status': 'ENTREGUE',
        'recebedor_nome': dados.recebedor_nome, 'entregue_em': data_utc(dados.entregue_em),
        'foto_sha256': foto.sha256, 'foto_bytes': len(foto.dados)}, origem='NUTRICAO_FILIPETA')
    await db.commit()
    await db.refresh(pedido)
    await db.refresh(pedido, attribute_names=['dieta', 'trabalhos_impressao'])
    await db.refresh(codigo)
    await db.refresh(comprovante, attribute_names=['registrado_em'])
    await gerenciador_ws.transmitir(pedido.filial_id, {'evento': 'status_alterado',
        'pedido': PedidoOut.model_validate(pedido).model_dump(mode='json')})
    return resumo_recebimento(codigo, pedido, filial, comprovante, privado=True)
