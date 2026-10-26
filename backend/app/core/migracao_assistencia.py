"""Evolução aditiva: pedidos antigos permanecem sem referência clínica presumida."""
from sqlalchemy import inspect


def migrar_assistencia(conn):
    if conn.dialect.name != "postgresql":
        return
    conn.exec_driver_sql("LOCK TABLE pedidos IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("pedidos")}
    if "prescricao" not in colunas:
        conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN prescricao JSONB")
    if "versao" not in colunas:
        conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN versao INTEGER NOT NULL DEFAULT 1")
