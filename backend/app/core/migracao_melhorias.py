"""Índice da central, sem modificar documentos ou enfileirar pedidos anteriores."""


def migrar_melhorias(conn):
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_impressao_data_id ON trabalhos_impressao (criado_em, id)")
