"""Acrescenta vínculo opcional com AD, preservando contas, senhas e sessões locais."""
from sqlalchemy import inspect


def migrar_ad(conexao):
    if conexao.dialect.name != "postgresql":
        return
    conexao.exec_driver_sql("LOCK TABLE usuarios IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conexao).get_columns("usuarios")}
    for nome, definicao in (
        ("origem_autenticacao", "VARCHAR(8) NOT NULL DEFAULT 'LOCAL'"),
        ("usuario_ad", "VARCHAR(254)"),
        ("ad_object_guid", "VARCHAR(36)"),
    ):
        if nome not in colunas:
            conexao.exec_driver_sql(f"ALTER TABLE usuarios ADD COLUMN {nome} {definicao}")
    conexao.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_ad ON usuarios (lower(usuario_ad))")
    conexao.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_ad_guid ON usuarios (ad_object_guid)")
