"""Mantém os trabalhos existentes como filipetas; não cria impressões históricas."""
from sqlalchemy import inspect


def migrar_etiquetas(conn):
    if conn.dialect.name != "postgresql":
        return
    conn.exec_driver_sql("LOCK TABLE trabalhos_impressao IN SHARE ROW EXCLUSIVE MODE")
    colunas = {c["name"] for c in inspect(conn).get_columns("trabalhos_impressao")}
    if "tipo_documento" not in colunas:
        conn.exec_driver_sql("ALTER TABLE trabalhos_impressao ADD COLUMN tipo_documento VARCHAR(20) NOT NULL DEFAULT 'FILIPETA'")
    if "configuracao" not in colunas:
        conn.exec_driver_sql("ALTER TABLE trabalhos_impressao ADD COLUMN configuracao JSONB")
    conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_impressao_ativa_tipo ON trabalhos_impressao (pedido_id, tipo_documento) WHERE estado IN ('PENDENTE', 'PROCESSANDO')")
    conn.exec_driver_sql("DROP INDEX IF EXISTS uq_impressao_ativa")
