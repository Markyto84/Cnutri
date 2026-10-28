from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import exigir_perfis
from ..models.models import Usuario
from ..services.recebimento_qr import ConsultaRecebimento, ConfirmacaoRecebimento, consultar_codigo, confirmar_recebimento, identificar_copeira, resumo_recebimento

router = APIRouter(prefix='/api/recebimentos', tags=['Recebimento por QR Code'])


@router.post('/consultar')
async def consultar(dados: ConsultaRecebimento, db: AsyncSession = Depends(get_db)):
    codigo, pedido, filial = await consultar_codigo(db, dados.codigo)
    return resumo_recebimento(codigo, pedido, filial)


@router.post('/identificar')
async def identificar(dados: ConsultaRecebimento, request: Request, db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis('COPEIRA'))):
    return await identificar_copeira(db, dados, request.client.host if request.client else None, usuario)


@router.post('/confirmar')
async def confirmar(dados: ConfirmacaoRecebimento, request: Request, db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfis('COPEIRA'))):
    return await confirmar_recebimento(db, dados, request.client.host if request.client else None, usuario)
