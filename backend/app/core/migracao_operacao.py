"""Acrescenta controle de repetição sem modificar pedidos existentes."""
from sqlalchemy import inspect


def migrar_operacao(conn):
    if conn.dialect.name != "postgresql":
        return
    conn.exec_driver_sql("LOCK TABLE pedidos IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("pedidos")}
    if "chave_envio" not in colunas:
        conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN chave_envio VARCHAR(36)")
    if "hash_envio" not in colunas:
        conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN hash_envio VARCHAR(64)")
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_pedido_chave_envio ON pedidos (filial_id, chave_envio)")
