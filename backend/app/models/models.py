"""Modelos SQLAlchemy — espelham o DDL da especificação técnica."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

# JSON portável: JSONB no PostgreSQL, JSON genérico nos demais bancos
JSONType = JSON().with_variant(JSONB, "postgresql")


class Perfil(Base):
    __tablename__ = "perfis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="perfil")


class Filial(Base):
    __tablename__ = "filiais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    codigo_slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    ip_impressora: Mapped[str | None] = mapped_column(String(45))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    dietas: Mapped[list["Dieta"]] = relationship(back_populates="filial", cascade="all, delete")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    nome_usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    # E-mails anteriores são preservados como dado legado, sem uso na autenticação.
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfis.id", ondelete="RESTRICT"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    troca_senha_obrigatoria: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    perfil: Mapped[Perfil] = relationship(back_populates="usuarios")
    filiais: Mapped[list["Filial"]] = relationship(
        secondary="usuarios_filiais", lazy="selectin"
    )
    __table_args__ = (Index("uq_usuarios_nome_usuario", func.lower(nome_usuario), unique=True),)


class UsuarioFilial(Base):
    __tablename__ = "usuarios_filiais"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id", ondelete="CASCADE"), primary_key=True)


class SessaoUsuario(Base):
    __tablename__ = "sessoes_usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime)


class LimiteLogin(Base):
    __tablename__ = "limites_login"

    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    falhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    janela_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Dieta(Base):
    __tablename__ = "dietas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    severa: Mapped[bool] = mapped_column(Boolean, default=False, comment="Dieta/restrição severa → destaque vermelho no Kanban")
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    filial: Mapped[Filial] = relationship(back_populates="dietas")


class FormularioConfig(Base):
    __tablename__ = "formularios_config"
    __table_args__ = (UniqueConstraint("filial_id", "tipo_publico", name="unique_filial_publico"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id", ondelete="CASCADE"), nullable=False)
    tipo_publico: Mapped[str] = mapped_column(String(20), nullable=False)  # MEDICO | ENFERMAGEM
    esquema_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id", ondelete="RESTRICT"), nullable=False)
    tipo_solicitacao: Mapped[str] = mapped_column(String(20), nullable=False)  # MEDICO | PACIENTE
    solicitante_identificacao: Mapped[str] = mapped_column(String(50), nullable=False)
    solicitante_nome: Mapped[str | None] = mapped_column(String(100))
    leito: Mapped[str | None] = mapped_column(String(30))
    prontuario: Mapped[str | None] = mapped_column(String(50))
    nome_paciente: Mapped[str | None] = mapped_column(String(100))
    dieta_id: Mapped[int | None] = mapped_column(ForeignKey("dietas.id", ondelete="SET NULL"))
    observacoes_alergias: Mapped[str | None] = mapped_column(Text)
    dados_dinamicos: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")
    ip_origem: Mapped[str | None] = mapped_column(String(45))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime)
    chave_envio: Mapped[str | None] = mapped_column(String(36))
    hash_envio: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("filial_id", "chave_envio", name="uq_pedido_chave_envio"),)

    filial: Mapped[Filial] = relationship()
    dieta: Mapped[Dieta | None] = relationship()
    historico: Mapped[list["HistoricoPedido"]] = relationship(back_populates="pedido", cascade="all, delete")
    trabalhos_impressao: Mapped[list["TrabalhoImpressao"]] = relationship(lazy="selectin", order_by="TrabalhoImpressao.id")

    @property
    def impressao(self):
        return self.estado_documento("FILIPETA")

    @property
    def etiqueta(self):
        return self.estado_documento("ETIQUETA")

    def estado_documento(self, tipo):
        trabalhos = [t for t in self.trabalhos_impressao if (t.tipo_documento or "FILIPETA") == tipo]
        if not trabalhos:
            return None
        trabalho = trabalhos[-1]
        return {"id": trabalho.id, "estado": trabalho.estado, "tentativas": trabalho.tentativas,
            "erro": trabalho.erro, "proxima_tentativa_em": trabalho.proxima_tentativa_em}


class TrabalhoImpressao(Base):
    __tablename__ = "trabalhos_impressao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="RESTRICT"), nullable=False, index=True)
    tipo_documento: Mapped[str] = mapped_column(String(20), nullable=False, default="FILIPETA", server_default="FILIPETA")
    configuracao: Mapped[dict | None] = mapped_column(JSONType)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE", index=True)
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    erro: Mapped[str | None] = mapped_column(String(250))
    dados: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime)
    reserva: Mapped[str | None] = mapped_column(String(36))
    solicitado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


Index("uq_impressao_ativa_tipo", TrabalhoImpressao.pedido_id, TrabalhoImpressao.tipo_documento, unique=True,
    postgresql_where=TrabalhoImpressao.estado.in_(("PENDENTE", "PROCESSANDO")),
    sqlite_where=TrabalhoImpressao.estado.in_(("PENDENTE", "PROCESSANDO")))


class ImpressoraEtiqueta(Base):
    __tablename__ = "impressoras_etiquetas"

    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id", ondelete="CASCADE"), primary_key=True)
    modelo: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    ip: Mapped[str | None] = mapped_column(String(45))
    porta: Mapped[int] = mapped_column(Integer, nullable=False, default=9100)
    protocolo: Mapped[str] = mapped_column(String(8), nullable=False, default="ZPL")
    resolucao: Mapped[int] = mapped_column(Integer, nullable=False, default=203)
    intervalo_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=2)


class HistoricoPedido(Base):
    __tablename__ = "historico_pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False)
    status_anterior: Mapped[str | None] = mapped_column(String(20))
    status_novo: Mapped[str] = mapped_column(String(20), nullable=False)
    alterado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    impresso: Mapped[bool] = mapped_column(Boolean, default=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pedido: Mapped[Pedido] = relationship(back_populates="historico")


class SessaoCopeira(Base):
    __tablename__ = "sessoes_copeiras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    filial_id: Mapped[int | None] = mapped_column(ForeignKey("filiais.id", ondelete="CASCADE"), index=True)
    presenca_ate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime)


class EntregaPedido(Base):
    __tablename__ = "entregas_pedidos"

    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="RESTRICT"), primary_key=True)
    copeira_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    copeira_nome: Mapped[str] = mapped_column(String(100), nullable=False)
    registrado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True)
    entregue_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ip_origem: Mapped[str | None] = mapped_column(String(45))


class RecebimentoEntrega(Base):
    __tablename__ = "recebimentos_entregas"

    pedido_id: Mapped[int] = mapped_column(ForeignKey("entregas_pedidos.pedido_id", ondelete="RESTRICT"), primary_key=True)
    recebedor_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    assinatura_png: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
