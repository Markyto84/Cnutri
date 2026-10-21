"""Detecção das credenciais públicas usadas pelas versões antigas."""
from sqlalchemy import select

from ..models.models import Usuario
from .security import verificar_senha


async def contas_com_senha_inicial(db):
    usuarios = (await db.execute(select(Usuario).where(Usuario.ativo.is_(True)))).scalars().all()
    return [u for u in usuarios if verificar_senha("Trocar@123", u.senha_hash)]


async def conferir_credenciais_producao(db):
    if await contas_com_senha_inicial(db):
        raise RuntimeError("Há contas com a senha inicial pública. Execute atualizar_seguranca.py antes de iniciar em produção")
