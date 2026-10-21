"""Amplia o esquema existente preservando contas e entregas históricas."""
from sqlalchemy import inspect


def migrar_seguranca(conn):
    if conn.dialect.name != "postgresql":
        return
    conn.exec_driver_sql("LOCK TABLE usuarios IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("usuarios")}
    if "troca_senha_obrigatoria" not in colunas:
        conn.exec_driver_sql("ALTER TABLE usuarios ADD COLUMN troca_senha_obrigatoria BOOLEAN NOT NULL DEFAULT false")
    if inspect(conn).has_table("entregas_pedidos"):
        colunas = {c["name"] for c in inspect(conn).get_columns("entregas_pedidos")}
        if "registrado_por_usuario_id" not in colunas:
            conn.exec_driver_sql("ALTER TABLE entregas_pedidos ADD COLUMN registrado_por_usuario_id INTEGER REFERENCES usuarios(id) ON DELETE RESTRICT")
