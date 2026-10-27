"""Adiciona o nome declarado sem modificar os recebimentos já registrados."""
from sqlalchemy import inspect


def migrar_recebimento_qr(conn):
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("LOCK TABLE recebimentos_qr IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("recebimentos_qr")}
    if "recebedor_nome" not in colunas:
        conn.exec_driver_sql("ALTER TABLE recebimentos_qr ADD COLUMN recebedor_nome VARCHAR(120)")
