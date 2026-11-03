import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis, verificar_acesso_filial
from ..models.models import ComprovanteEntrega, Usuario
from ..services.foto_comprovante import MAX_UPLOAD_BYTES, otimizar_foto
from ..services.recebimento_qr import ConsultaRecebimento, ConfirmacaoRecebimento, consultar_codigo, confirmar_recebimento, resumo_recebimento

router = APIRouter(prefix='/api/recebimentos', tags=['Comprovação da entrega pela Nutrição'])
PERFIS_RECEBIMENTO = ('NUTRICIONISTA', 'ADMIN_TI')
_processamento_fotos = asyncio.Semaphore(2)


@router.post('/consultar')
async def consultar(dados: ConsultaRecebimento, db: AsyncSession = Depends(get_db)):
    codigo, pedido, filial = await consultar_codigo(db, dados.codigo)
    comprovante = await db.get(ComprovanteEntrega, pedido.id)
    return resumo_recebimento(codigo, pedido, filial, comprovante)


@router.post('/detalhes')
async def detalhes(dados: ConsultaRecebimento, db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis(*PERFIS_RECEBIMENTO))):
    codigo, pedido, filial = await consultar_codigo(db, dados.codigo)
    await verificar_acesso_filial(filial.id, usuario, db)
    comprovante = await db.get(ComprovanteEntrega, pedido.id)
    return resumo_recebimento(codigo, pedido, filial, comprovante, privado=True)


@router.post('/identificar')
async def identificar(_: Usuario = Depends(exigir_perfis(*PERFIS_RECEBIMENTO))):
    raise HTTPException(410, 'O painel de entregas das copeiras foi desativado. A Nutrição deve lançar a filipeta assinada pelo QR Code')


@router.post('/confirmar')
async def confirmar(request: Request,
    codigo: Annotated[str, Form(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]{43}$')],
    recebedor_nome: Annotated[str, Form(min_length=3, max_length=120)],
    entregue_em: Annotated[datetime, Form()],
    foto: Annotated[UploadFile, File()],
    db: AsyncSession = Depends(get_db), usuario: Usuario = Depends(exigir_perfis(*PERFIS_RECEBIMENTO))):
    try:
        dados = ConfirmacaoRecebimento(codigo=codigo, recebedor_nome=recebedor_nome, entregue_em=entregue_em)
    except ValidationError as erro:
        raise HTTPException(422, erro.errors()[0]['msg'].removeprefix('Value error, ')) from None
    # Autoriza a unidade antes de decodificar a foto e só bloqueia o pedido ao gravar.
    _, pedido, filial = await consultar_codigo(db, codigo)
    await verificar_acesso_filial(filial.id, usuario, db)
    try:
        if foto.size is not None and foto.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'A foto deve ter no máximo 12 MB')
        conteudo = await foto.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await foto.close()
    async with _processamento_fotos:
        otimizada = await run_in_threadpool(otimizar_foto, conteudo)
    return await confirmar_recebimento(db, dados, otimizada, request.client.host if request.client else None, usuario)
