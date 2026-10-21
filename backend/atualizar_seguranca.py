"""Substitui somente senhas iniciais antigas e entrega os novos acessos em arquivo privado."""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import secrets

from configurar_ambiente import BACKEND, gravar_privado
from app.core.credenciais_iniciais import contas_com_senha_inicial
from app.core.database import SessionLocal, engine
from app.core.login_usuarios import migrar_login_usuarios
from app.core.migracao_seguranca import migrar_seguranca
from app.core.security import hash_senha
from app.core.sessoes import revogar_sessoes
from app.models.models import Base


async def atualizar(arquivo: Path):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(migrar_login_usuarios)
        await conn.run_sync(migrar_seguranca)
    async with SessionLocal() as db:
        contas = await contas_com_senha_inicial(db)
        if not contas:
            print("Nenhuma conta ativa usa a senha inicial antiga. Nenhuma senha foi alterada.")
            return
        if arquivo.exists():
            raise RuntimeError("O arquivo de entrega já existe. Escolha outro caminho para preservá-lo")
        linhas = ["CNUTRI — ACESSOS TEMPORÁRIOS", "", "Acesse /login e defina uma nova senha no primeiro acesso.",
            "Não envie este arquivo por chat nem o inclua no Git. Guarde-o sob responsabilidade da TI.", ""]
        for usuario in contas:
            senha = secrets.token_urlsafe(24)
            linhas.extend([f"Usuário: {usuario.nome_usuario}", f"Senha temporária: {senha}", ""])
            usuario.senha_hash = hash_senha(senha)
            usuario.troca_senha_obrigatoria = True
            await revogar_sessoes(db, usuario.id)
        # Falhar ao proteger/gravar o arquivo impede o commit das novas senhas.
        gravar_privado(arquivo, "\n".join(linhas))
        try:
            await db.commit()
        except Exception:
            gravar_privado(arquivo, "Atualização NÃO concluída. As senhas temporárias foram descartadas.\n")
            raise
        print(f"{len(contas)} contas atualizadas. Acessos temporários somente em: {arquivo}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", type=Path, default=BACKEND.parent / "work" / f"acessos-temporarios-{datetime.now():%Y%m%d-%H%M%S}.txt")
    args = parser.parse_args()
    asyncio.run(atualizar(args.arquivo.resolve()))
