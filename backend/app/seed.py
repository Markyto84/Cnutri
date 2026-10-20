"""Seed inicial: perfis, utilizadores, filial de demonstração, dietas e formulários padrão."""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .core.security import hash_senha
from .models.models import (
    Dieta,
    Filial,
    FormularioConfig,
    Perfil,
    Usuario,
    UsuarioFilial,
)
from .api.gestao import ESQUEMA_PADRAO_ENFERMAGEM, ESQUEMA_PADRAO_MEDICO

logger = logging.getLogger(__name__)

DIETAS_DEMO = [
    ("Geral", "Dieta normal / livre", False),
    ("Branda", "Dieta branda, de fácil digestão", False),
    ("Pastosa", "Consistência pastosa", False),
    ("Líquida", "Apenas líquidos", False),
    ("Hipossódica", "Baixo teor de sódio", False),
    ("Enteral", "Nutrição enteral — ATENÇÃO à via", True),
]

USUARIOS_DEMO = [
    ("Administrador TI", "admin@hospital.local", "Trocar@123", "ADMIN_TI"),
    ("Nutricionista Demo", "nutricao@hospital.local", "Trocar@123", "NUTRICIONISTA"),
    ("Cozinha Demo", "cozinha@hospital.local", "Trocar@123", "COZINHA"),
]


async def executar_seed(db: AsyncSession) -> None:
    # Novos perfis também devem ser criados nas bases já existentes.
    if (await db.execute(select(Perfil).where(Perfil.nome == "COPEIRA"))).scalar_one_or_none() is None:
        db.add(Perfil(nome="COPEIRA"))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()  # outro processo pode ter criado o mesmo perfil
    total = (await db.execute(select(func.count(Filial.id)))).scalar_one()
    if total > 0:
        return  # base já inicializada

    logger.info("Base vazia — executando seed inicial...")

    perfis = {}
    for nome in ("ADMIN_TI", "NUTRICIONISTA", "COZINHA"):
        perfil = (await db.execute(select(Perfil).where(Perfil.nome == nome))).scalar_one_or_none()
        if perfil is None:
            perfil = Perfil(nome=nome)
            db.add(perfil)
            await db.flush()
        perfis[nome] = perfil

    filial = Filial(nome="Centro Médico Prevent Senior Havaí", codigo_slug="unidade-havai", ip_impressora=None)
    db.add(filial)
    await db.flush()

    for nome, email, senha, perfil_nome in USUARIOS_DEMO:
        usuario = Usuario(
            nome=nome, email=email, senha_hash=hash_senha(senha), perfil_id=perfis[perfil_nome].id
        )
        db.add(usuario)
        await db.flush()
        db.add(UsuarioFilial(usuario_id=usuario.id, filial_id=filial.id))

    dietas = [Dieta(filial_id=filial.id, nome=n, descricao=d, severa=s) for n, d, s in DIETAS_DEMO]
    db.add_all(dietas)

    db.add_all(
        [
            FormularioConfig(filial_id=filial.id, tipo_publico="MEDICO", esquema_json=ESQUEMA_PADRAO_MEDICO),
            FormularioConfig(filial_id=filial.id, tipo_publico="ENFERMAGEM", esquema_json=ESQUEMA_PADRAO_ENFERMAGEM),
        ]
    )

    await db.commit()
    logger.info("Seed concluído: 1 filial, 3 utilizadores, %s dietas.", len(dietas))
