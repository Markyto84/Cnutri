"""Limitação persistida das tentativas de autenticação, compartilhada entre workers."""
from datetime import timedelta
from hashlib import sha256
import logging
from math import ceil

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models.models import LimiteLogin
from .presenca import agora_utc

logger = logging.getLogger("cnutri.seguranca")
JANELA = timedelta(minutes=15)


async def conferir_limites(db, ip: str, login: str):
    agora = agora_utc()
    registros = []
    for texto, limite in sorted(((f"ip:{ip}", 100), (f"login:{ip}:{login}", 5))):
        chave = sha256(texto.encode()).hexdigest()
        inserir = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        await db.execute(inserir(LimiteLogin).values(chave=chave, falhas=0, janela_inicio=agora).on_conflict_do_nothing(index_elements=["chave"]))
        registro = await db.scalar(select(LimiteLogin).where(LimiteLogin.chave == chave).with_for_update())
        if agora >= registro.janela_inicio + JANELA:
            registro.janela_inicio, registro.falhas = agora, 0
        if registro.falhas >= limite:
            logger.warning("autenticacao_limitada ip=%s", ip)
            espera = max(1, ceil((registro.janela_inicio + JANELA - agora).total_seconds()))
            await db.commit()
            raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente", headers={"Retry-After": str(espera)})
        registros.append(registro)
    return registros
