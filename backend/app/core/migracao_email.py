"""Parâmetros SMTP opcionais, preservando os modelos e credenciais anteriores."""
from sqlalchemy import inspect


def migrar_email(conn):
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("LOCK TABLE configuracoes_email_unidades IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("configuracoes_email_unidades")}
    for nome, tipo in (("servidor", "VARCHAR(253)"), ("porta", "INTEGER"),
        ("seguranca", "VARCHAR(12)"), ("autenticar", "BOOLEAN"), ("usuario", "VARCHAR(254)"),
        ("servidor_secundario", "VARCHAR(253)"), ("porta_secundaria", "INTEGER"),
        ("tempo_limite", "INTEGER"), ("endereco_resposta", "VARCHAR(254)")):
        if nome not in colunas:
            conn.exec_driver_sql(f"ALTER TABLE configuracoes_email_unidades ADD COLUMN {nome} {tipo}")
