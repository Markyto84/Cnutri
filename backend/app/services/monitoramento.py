"""Saúde operacional agregada, sem documentos, credenciais ou dados pessoais."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import time
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import aliased

from ..models.models import Pedido, TrabalhoImpressao
from .operacao import data_utc


def agora():
    return datetime.now(timezone.utc)


@dataclass
class SinalFila:
    ativa: bool = False
    ultimo_ciclo_em: datetime | None = None
    ultimo_sucesso_em: datetime | None = None
    falhas_consecutivas: int = 0

    def registrar(self, sucesso):
        self.ultimo_ciclo_em = agora()
        if sucesso:
            self.ultimo_sucesso_em = self.ultimo_ciclo_em
            self.falhas_consecutivas = 0
        else:
            self.falhas_consecutivas += 1

    def resumo(self):
        recente = self.ultimo_ciclo_em and (agora() - self.ultimo_ciclo_em).total_seconds() < 120
        estado = "ATIVA" if self.ativa and recente and not self.falhas_consecutivas else "ATENCAO" if self.ativa else "PARADA"
        return {"estado": estado, "ultimo_ciclo_em": data_utc(self.ultimo_ciclo_em),
                "ultimo_sucesso_em": data_utc(self.ultimo_sucesso_em), "falhas_consecutivas": self.falhas_consecutivas}


@dataclass
class EstadoMonitoramento:
    iniciada_em: datetime = field(default_factory=agora)
    inicio_monotono: float = field(default_factory=time.monotonic)
    fila: SinalFila = field(default_factory=SinalFila)


class TesteBackup(BaseModel):
    estado: Literal["VALIDADO", "FALHOU", "EM_ANDAMENTO"]
    iniciado_em: datetime
    concluido_em: datetime | None = None
    duracao_segundos: float | None = Field(default=None, ge=0)
    tabelas_verificadas: int = Field(default=0, ge=0)
    registros_verificados: int = Field(default=0, ge=0)
    assinaturas_verificadas: int = Field(default=0, ge=0)
    formularios_verificados: int = Field(default=0, ge=0)
    sequencias_verificadas: int = Field(default=0, ge=0)
    temporario_removido: bool = False

    @model_validator(mode="after")
    def conferir_validacao(self):
        if self.estado == "VALIDADO" and (not self.concluido_em or not self.temporario_removido or self.tabelas_verificadas < 1):
            raise ValueError("Validação não concluída")
        return self


class RelatorioBackup(BaseModel):
    versao: Literal[1]
    ultimo_teste: TesteBackup
    ultima_validacao: TesteBackup | None = None


def ler_recuperacao(caminho):
    try:
        with caminho.open("rb") as arquivo:
            conteudo = arquivo.read(65537)
        if len(conteudo) > 65536:
            raise ValueError("Relatório acima do limite")
        resultado = RelatorioBackup.model_validate_json(conteudo)
        if resultado.ultima_validacao and resultado.ultima_validacao.estado != "VALIDADO":
            raise ValueError("Estado inconsistente")
        return {"estado": resultado.ultimo_teste.estado, **resultado.model_dump(mode="json", exclude={"versao"})}
    except FileNotFoundError:
        return {"estado": "SEM_TESTE", "ultimo_teste": None, "ultima_validacao": None}
    except (OSError, ValueError, ValidationError):
        return {"estado": "INCONSISTENTE", "ultimo_teste": None, "ultima_validacao": None}


async def sondar_banco(db):
    inicio = time.monotonic()
    try:
        async with asyncio.timeout(3):
            await db.execute(text("SELECT 1"))
        return {"estado": "CONECTADO", "latencia_ms": round((time.monotonic() - inicio) * 1000, 1)}
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"estado": "INDISPONIVEL", "latencia_ms": None}


async def resumo_fila(db):
    instante = agora().replace(tzinfo=None)
    # Pendências de qualquer data; contadores históricos ficam limitados às últimas 24h.
    linhas = (await db.execute(select(TrabalhoImpressao.estado, func.count())
        .where((TrabalhoImpressao.criado_em >= instante - timedelta(hours=24))
            | TrabalhoImpressao.estado.in_(("PENDENTE", "PROCESSANDO")))
        .group_by(TrabalhoImpressao.estado))).all()
    contadores = {e: 0 for e in ("PENDENTE", "PROCESSANDO", "ENVIADO", "FALHA", "INCERTO", "CANCELADO")}
    contadores.update(dict(linhas))
    anterior = aliased(TrabalhoImpressao)
    ultimo = select(func.max(anterior.id)).where(anterior.pedido_id == TrabalhoImpressao.pedido_id,
        anterior.tipo_documento == TrabalhoImpressao.tipo_documento).correlate(TrabalhoImpressao).scalar_subquery()
    problemas = dict((await db.execute(select(TrabalhoImpressao.estado, func.count()).select_from(TrabalhoImpressao)
        .join(Pedido, Pedido.id == TrabalhoImpressao.pedido_id).where(TrabalhoImpressao.id == ultimo,
            TrabalhoImpressao.estado.in_(("FALHA", "INCERTO")), Pedido.status.in_(("PENDENTE", "EM_PREPARO", "PRONTO")),
            (TrabalhoImpressao.tipo_documento != "ETIQUETA") | (Pedido.status == "PRONTO"))
        .group_by(TrabalhoImpressao.estado))).all())
    pendente_desde = await db.scalar(select(func.min(TrabalhoImpressao.criado_em)).where(TrabalhoImpressao.estado == "PENDENTE"))
    atrasados = await db.scalar(select(func.count()).select_from(TrabalhoImpressao).where(
        TrabalhoImpressao.estado == "PROCESSANDO", TrabalhoImpressao.iniciado_em < instante - timedelta(seconds=60)))
    return {"contadores_24h": contadores, "falhas_atuais": problemas.get("FALHA", 0),
            "incertos_atuais": problemas.get("INCERTO", 0), "pendente_mais_antigo_em": data_utc(pendente_desde),
            "processando_mais_60s": atrasados}


async def obter_monitoramento(db, estado, caminho_relatorio):
    banco = await sondar_banco(db)
    fila = None
    if banco["estado"] == "CONECTADO":
        try:
            async with asyncio.timeout(3):
                fila = await resumo_fila(db)
                banco["tamanho_bytes"] = await db.scalar(text("SELECT pg_database_size(current_database())")) if db.bind.dialect.name == "postgresql" else None
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            banco["consultas_operacionais"] = "INDISPONIVEIS"
    return {"consultado_em": agora().isoformat(),
            "api": {"estado": "RESPONDENDO", "iniciada_em": estado.iniciada_em.isoformat(),
                    "tempo_ativo_segundos": max(0, int(time.monotonic() - estado.inicio_monotono))},
            "banco": banco, "consumidor": estado.fila.resumo(), "fila": fila,
            "recuperacao": await asyncio.to_thread(ler_recuperacao, caminho_relatorio)}
