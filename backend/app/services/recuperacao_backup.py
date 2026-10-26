"""Recuperação em banco temporário. Nunca conecta uma API ou consumidor à cópia."""
import asyncio
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from PIL import Image
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload

from ..models.models import FormularioConfig, Pedido, RecebimentoEntrega
from ..schemas.schemas import PedidoOut
from .validacao_pedidos import validar_esquema


def validar_alvo(nome, origem):
    if nome == origem or not re.fullmatch(r"cnutri_restore_[0-9a-f]{32}", nome):
        raise ValueError("Destino de restauração inválido")


def tabela_sql(conn, nome):
    return '"public".' + conn.engine.dialect.identifier_preparer.quote(nome)


def normalizar_indice(definicao):
    # O pg_dump pode distribuir o cast varchar[] -> text[] pelos elementos da
    # lista. Canonicaliza somente esses casts equivalentes, preservando predicado,
    # literais, colunas e unicidade. A definição normalizada nunca é executada.
    literal = r"('(?:[^']|'')*')"
    definicao = re.sub(r"\(" + literal + r"::character varying\)::text", r"\1::text", definicao)
    definicao = re.sub(literal + r"::character varying", r"\1::text", definicao)
    return re.sub(r"\(\(ARRAY\[([^\]]*)\]\)::text\[\]\)", r"(ARRAY[\1])", definicao)


async def descrever_estrutura(conn):
    colunas = (await conn.execute(text("""SELECT table_name, column_name, ordinal_position,
        udt_name, is_nullable, column_default, character_maximum_length, numeric_precision,
        numeric_scale, datetime_precision, collation_name FROM information_schema.columns
        WHERE table_schema='public' ORDER BY table_name, ordinal_position"""))).all()
    restricoes = (await conn.execute(text("""SELECT c.relname, k.conname, k.contype,
        k.convalidated, pg_get_constraintdef(k.oid, true) FROM pg_constraint k
        JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' ORDER BY c.relname, k.conname"""))).all()
    indices = (await conn.execute(text("""SELECT t.relname, i.relname, x.indisvalid, x.indisready,
        pg_get_indexdef(i.oid) FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_class t ON t.oid=x.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' ORDER BY t.relname,i.relname"""))).all()
    indices = [[*linha[:-1], normalizar_indice(linha[-1])] for linha in indices]
    return [list(map(list, linhas)) for linhas in (colunas, restricoes, indices)]


async def estrutura(conn):
    conteudo = json.dumps(await descrever_estrutura(conn), default=str, ensure_ascii=False)
    return hashlib.sha256(conteudo.encode()).hexdigest()


async def resumir_tabelas(conn):
    await conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    nomes = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
    resultado = {}
    for nome in sorted(nomes):
        pk = await conn.run_sync(lambda c: inspect(c).get_pk_constraint(nome, schema="public")["constrained_columns"])
        ordem = ", ".join(conn.engine.dialect.identifier_preparer.quote(c) for c in pk) if pk else "resumo"
        consulta = text(f"SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') AS resumo FROM {tabela_sql(conn, nome)} t ORDER BY {ordem}")
        resumo, quantidade = hashlib.sha256(), 0
        linhas = await conn.stream(consulta)
        async for linha in linhas:
            resumo.update(bytes.fromhex(linha.resumo))
            quantidade += 1
        resultado[nome] = {"registros": quantidade, "sha256": resumo.hexdigest()}
    return resultado


async def conferir_sequencias(conn):
    quantidade = 0
    for nome in await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public")):
        pk = await conn.run_sync(lambda c: inspect(c).get_pk_constraint(nome, schema="public")["constrained_columns"])
        for coluna in pk:
            nome_seq = await conn.scalar(text("SELECT pg_get_serial_sequence(:tabela,:coluna)"), {"tabela": tabela_sql(conn, nome), "coluna": coluna})
            if not nome_seq:
                continue
            seq = (await conn.execute(text("""SELECT n.nspname, c.relname, s.seqincrement FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_sequence s ON s.seqrelid=c.oid
                WHERE c.oid=CAST(:sequencia AS regclass)"""), {"sequencia": nome_seq})).one()
            quote = conn.engine.dialect.identifier_preparer.quote
            ultimo, chamado = (await conn.execute(text(f"SELECT last_value,is_called FROM {quote(seq.nspname)}.{quote(seq.relname)}"))).one()
            maior = await conn.scalar(text(f"SELECT max({quote(coluna)}) FROM {tabela_sql(conn, nome)}"))
            proximo = ultimo + seq.seqincrement if chamado else ultimo
            if seq.seqincrement <= 0 or (maior is not None and proximo <= maior):
                raise ValueError("Sequência restaurada incompatível com os registros")
            quantidade += 1
    return quantidade


async def conferir_aplicacao(conn):
    formularios = assinaturas = pedidos = 0
    async with AsyncSession(bind=conn, expire_on_commit=False) as db:
        for config in (await db.scalars(select(FormularioConfig))).all():
            validar_esquema(config.esquema_json)
            formularios += 1
        linhas = await db.stream_scalars(select(Pedido).options(selectinload(Pedido.dieta),
            selectinload(Pedido.trabalhos_impressao)).execution_options(yield_per=100))
        async for pedido in linhas:
            PedidoOut.model_validate(pedido)
            pedidos += 1
        linhas = await db.stream_scalars(select(RecebimentoEntrega.assinatura_png).execution_options(yield_per=100))
        async for dados in linhas:
            with Image.open(BytesIO(dados)) as imagem:
                if imagem.format != "PNG" or not (0 < imagem.width <= 4096 and 0 < imagem.height <= 4096):
                    raise ValueError("Assinatura restaurada inválida")
                imagem.verify()
            assinaturas += 1
    return {"formularios_verificados": formularios, "assinaturas_verificadas": assinaturas, "pedidos_verificados": pedidos}


class ComandosPostgres:
    def __init__(self, container, usuario):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", container):
            raise ValueError("Nome do contêiner inválido")
        self.container, self.usuario = container, usuario

    async def executar(self, programa, argumentos=(), entrada=None, saida=None):
        comando = ["docker", "exec"] + (["-i"] if entrada is not None else []) + [self.container, programa, "-U", self.usuario, *argumentos]
        resposta = await asyncio.to_thread(subprocess.run, comando, stdin=entrada,
            stdout=saida if saida is not None else subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, check=True)
        if resposta.stderr and resposta.stderr.strip():
            raise RuntimeError("O comando PostgreSQL emitiu avisos; requer conferência")
        return resposta.stdout


async def recuperar_e_conferir(url, container, pasta_backup, progresso=None):
    """Gera sua própria cópia, restaura/valida e remove só o banco UUID que criou."""
    url = make_url(url)
    if url.drivername != "postgresql+asyncpg" or not url.database or not url.username:
        raise ValueError("Requer PostgreSQL/asyncpg configurado")
    alvo = "cnutri_restore_" + uuid4().hex
    validar_alvo(alvo, url.database)
    comandos = ComandosPostgres(container, url.username)
    origem_engine = create_async_engine(url)
    destino_engine = None
    criado = removido = False
    inicio = datetime.now(timezone.utc).isoformat()
    relogio = time.monotonic()
    arquivo = pasta_backup / ("cnutri-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8] + ".dump")
    etapa = "origem"
    resultado = {"estado": "EM_ANDAMENTO", "iniciado_em": inicio, "temporario_removido": False}
    if progresso:
        progresso(dict(resultado))
    try:
        async with origem_engine.connect() as origem:
            id_host = await origem.scalar(text("SELECT system_identifier::text FROM pg_control_system()"))
            id_container = (await comandos.executar("psql", ["-X", "-At", "-d", url.database, "-c", "SELECT system_identifier::text FROM pg_control_system()"])).decode().strip()
            if id_host != id_container:
                raise ValueError("O contêiner não corresponde ao banco configurado")
            bloqueado = await origem.scalar(text("SELECT pg_try_advisory_lock(hashtext(current_database()), 263016)"))
            if not bloqueado:
                raise ValueError("Outro teste de recuperação está em execução")
            await origem.commit()
            origem = await origem.execution_options(isolation_level="REPEATABLE READ")
            async with origem.begin():
                await origem.execute(text("SET TRANSACTION READ ONLY"))
                snapshot = await origem.scalar(text("SELECT pg_export_snapshot()"))
                propriedades = (await origem.execute(text("SELECT pg_encoding_to_char(encoding), datcollate, datctype, datlocprovider, daticulocale FROM pg_database WHERE datname=current_database()"))).one()
                etapa = "backup"
                from configurar_ambiente import gravar_privado
                gravar_privado(arquivo, "")
                with arquivo.open("wb") as saida:
                    await comandos.executar("pg_dump", ["-d", url.database, "-Fc", "--no-owner", "--no-privileges", "--snapshot", snapshot], saida=saida)
                etapa = "resumos_da_origem"
                anterior, esquema = await resumir_tabelas(origem), await estrutura(origem)
            etapa = "criacao_temporaria"
            argumentos = ["--template=template0", "--encoding=" + propriedades[0], "--lc-collate=" + propriedades[1], "--lc-ctype=" + propriedades[2],
                          "--locale-provider=" + ("icu" if propriedades[3] == "i" else "libc")]
            if propriedades[3] == "i":
                argumentos.append("--icu-locale=" + propriedades[4])
            await comandos.executar("createdb", [*argumentos, alvo])
            criado = True
            # A cópia não fica disponível para conexões concedidas a PUBLIC.
            await comandos.executar("psql", ["-X", "-v", "ON_ERROR_STOP=1", "-d", alvo, "-c", f'REVOKE CONNECT ON DATABASE "{alvo}" FROM PUBLIC'])
            etapa = "restauracao"
            with arquivo.open("rb") as entrada:
                await comandos.executar("pg_restore", ["-d", alvo, "--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges"], entrada=entrada)
            etapa = "conferencia_conteudo"
            destino_engine = create_async_engine(url.set(database=alvo))
            async with destino_engine.connect() as destino:
                await destino.execute(text("SET TRANSACTION READ ONLY"))
                if (await resumir_tabelas(destino)) != anterior:
                    raise ValueError("Conteúdo divergente após a restauração")
                etapa = "conferencia_estrutura"
                if await estrutura(destino) != esquema:
                    raise ValueError("Estrutura divergente após a restauração")
                etapa = "conferencia_sequencias"
                sequencias = await conferir_sequencias(destino)
                etapa = "conferencia_aplicacao"
                aplicacao = await conferir_aplicacao(destino)
            resultado.update({"tabelas_verificadas": len(anterior), "registros_verificados": sum(t["registros"] for t in anterior.values()),
                "sequencias_verificadas": sequencias, **aplicacao, "tabelas": anterior, "estrutura_sha256": esquema,
                "backup_nome": arquivo.name, "backup_bytes": arquivo.stat().st_size})
    except Exception as exc:
        resultado.update(estado="FALHOU", etapa=etapa, erro_tipo=type(exc).__name__)
    finally:
        if destino_engine:
            await destino_engine.dispose()
        if criado:
            try:
                validar_alvo(alvo, url.database)
                await comandos.executar("dropdb", [alvo])
                removido = True
            except Exception as exc:
                resultado.update(estado="FALHOU", etapa="limpeza", erro_tipo=type(exc).__name__)
                resultado["temporario_pendente"] = alvo
        await origem_engine.dispose()  # Também libera a trava consultiva, inclusive em falhas.
        resultado.update(temporario_removido=removido, concluido_em=datetime.now(timezone.utc).isoformat(),
            duracao_segundos=round(time.monotonic() - relogio, 2))
    if resultado["estado"] != "FALHOU":
        resultado["estado"] = "VALIDADO"
    return resultado
