"""Nomes de acesso e migração das contas PostgreSQL existentes, sem alterar senhas."""
import re
import unicodedata

from sqlalchemy import inspect, text

PADRAO_USUARIO = r"^[a-z0-9][a-z0-9._-]{2,49}$"


def normalizar_usuario(valor: str) -> str:
    return valor.strip().lower()


def usuario_inicial(email: str | None, usuario_id: int, ocupados: set[str]) -> str:
    base = unicodedata.normalize("NFKD", (email or "").split("@", 1)[0]).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9._-]+", "_", base).strip("._-")[:50]
    if len(base) < 3:
        base = f"usuario{usuario_id}"
    candidato, tentativa = base, 0
    while candidato in ocupados:
        tentativa += 1
        sufixo = f"_{usuario_id}" + (f"_{tentativa}" if tentativa > 1 else "")
        candidato = base[:50 - len(sufixo)] + sufixo
    ocupados.add(candidato)
    return candidato


def migrar_login_usuarios(conexao):
    # O banco da aplicação é PostgreSQL. Os testes SQLite criam o esquema atual
    # diretamente com metadata.create_all, sem precisar de ALTER COLUMN.
    if conexao.dialect.name != "postgresql":
        return
    conexao.exec_driver_sql("LOCK TABLE usuarios IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"]: c for c in inspect(conexao).get_columns("usuarios")}
    if "nome_usuario" not in colunas:
        conexao.exec_driver_sql("ALTER TABLE usuarios ADD COLUMN nome_usuario VARCHAR(50)")
    registros = conexao.execute(text("SELECT id, email, nome_usuario FROM usuarios ORDER BY id")).mappings().all()
    ocupados = {r["nome_usuario"].lower() for r in registros if r["nome_usuario"]}
    for registro in registros:
        if not registro["nome_usuario"]:
            nome = usuario_inicial(registro["email"], registro["id"], ocupados)
            conexao.execute(text("UPDATE usuarios SET nome_usuario = :nome WHERE id = :id"), {"nome": nome, "id": registro["id"]})
    conexao.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_nome_usuario ON usuarios (lower(nome_usuario))")
    if "nome_usuario" not in colunas or colunas["nome_usuario"]["nullable"]:
        conexao.exec_driver_sql("ALTER TABLE usuarios ALTER COLUMN nome_usuario SET NOT NULL")
    if not colunas["email"]["nullable"]:
        conexao.exec_driver_sql("ALTER TABLE usuarios ALTER COLUMN email DROP NOT NULL")
