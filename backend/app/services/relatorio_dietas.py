"""Consultas do relatório de solicitações: mesmo recorte na tela e na exportação."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import case, func, select

from ..models.models import Dieta, EntregaPedido, Filial, Pedido, RecebimentoEntrega, Usuario
from .operacao import data_utc

BRASILIA = timezone(timedelta(hours=-3))
STATUS = {"PENDENTE": "Pendente", "EM_PREPARO": "Em preparo", "PRONTO": "Pronto", "ENTREGUE": "Entregue", "CANCELADO": "Cancelado"}
TIPOS = {"PACIENTE": "Enfermagem", "MEDICO": "Médico"}
CHAVES_STATUS = {"PENDENTE": "pendentes", "EM_PREPARO": "em_preparo", "PRONTO": "prontos", "ENTREGUE": "entregues", "CANCELADO": "cancelados"}


@dataclass
class ConsultaDietas:
    filtros: list
    contexto: dict


def consulta_base(consulta: ConsultaDietas):
    return (select(Pedido, Filial.nome, Dieta.nome, EntregaPedido.entregue_em,
        EntregaPedido.copeira_nome, RecebimentoEntrega.recebedor_nome, Usuario.nome, Filial.codigo_slug)
        .join(Filial, Filial.id == Pedido.filial_id)
        .outerjoin(Dieta, Dieta.id == Pedido.dieta_id)
        .outerjoin(EntregaPedido, EntregaPedido.pedido_id == Pedido.id)
        .outerjoin(RecebimentoEntrega, RecebimentoEntrega.pedido_id == Pedido.id)
        .outerjoin(Usuario, Usuario.id == EntregaPedido.registrado_por_usuario_id)
        .where(*consulta.filtros))


async def resumir(db, consulta: ConsultaDietas):
    categoria = func.coalesce(Dieta.nome, case((Pedido.tipo_solicitacao == "MEDICO", "Refeição médica"), else_="Dieta não informada"))
    linhas = (await db.execute(consulta_base(consulta).with_only_columns(
        Filial.id, Filial.codigo_slug, Filial.nome, Dieta.id, categoria, Pedido.status, func.count(Pedido.id), maintain_column_froms=True,
    ).group_by(Filial.id, Filial.codigo_slug, Filial.nome, Dieta.id, categoria, Pedido.status).order_by(Filial.nome, Filial.id, categoria))).all()
    return agrupar(linhas)


def agrupar(linhas):
    grupos = {}
    totais = {"total": 0, **dict.fromkeys(CHAVES_STATUS.values(), 0)}
    for unidade_id, codigo, unidade, dieta_id, dieta, status, quantidade in linhas:
        grupo = grupos.setdefault((unidade_id, dieta_id, dieta), {"unidade_id": unidade_id, "unidade_codigo": codigo, "unidade": unidade, "dieta_id": dieta_id, "dieta": dieta,
            "total": 0, **dict.fromkeys(CHAVES_STATUS.values(), 0)})
        grupo["total"] += quantidade
        totais["total"] += quantidade
        if status in CHAVES_STATUS:
            grupo[CHAVES_STATUS[status]] += quantidade
            totais[CHAVES_STATUS[status]] += quantidade
    return sorted(grupos.values(), key=lambda g: (g["unidade"], g["unidade_id"], g["dieta"], g["dieta_id"] or 0)), totais


def texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return str(valor)


def detalhar(linha):
    pedido, unidade, dieta, entregue_em, copeira, recebedor, operador, codigo = linha
    dados = pedido.dados_dinamicos or {}
    referencia = pedido.prescricao or {}
    campos = ("refeicao", "cardapio", "cardapio_acompanhante", "para", "equipe", "horario_entrega", "suco", "sobremesa", "liquido_espessado", "internado_mais_6h")
    extras = {k: v for k, v in dados.items() if k not in {*campos, "andar", "local_entrega", "sexo", "data_nascimento", "matricula", "prontuario"}}
    return {"pedido_id": pedido.id, "unidade_id": pedido.filial_id, "unidade_codigo": codigo, "dieta_id": pedido.dieta_id, "unidade": unidade, "criado_em": data_utc(pedido.criado_em),
        "tipo_solicitacao": pedido.tipo_solicitacao, "status": pedido.status,
        "destinatario": pedido.nome_paciente or pedido.solicitante_nome or "",
        "leito": pedido.leito or "", "local_entrega": texto(dados.get("local_entrega") or dados.get("andar")),
        "dieta": dieta or ("Refeição médica" if pedido.tipo_solicitacao == "MEDICO" else "Dieta não informada"),
        **{campo: texto(dados.get(campo)) for campo in campos},
        "observacoes_alergias": pedido.observacoes_alergias or "", "solicitante_nome": pedido.solicitante_nome or "",
        "concluido_em": data_utc(pedido.concluido_em), "entregue_em": data_utc(entregue_em),
        "copeira_nome": copeira or "", "recebedor_nome": recebedor or "", "registrado_por_nome": operador or "", "assinatura_registrada": recebedor is not None,
        "outros_campos": texto(extras) if extras else "",
        "solicitante_identificacao": pedido.solicitante_identificacao, "versao_pedido": pedido.versao,
        "prescricao_referencia": referencia.get("referencia", ""), "prescricao_data_hora": referencia.get("data_hora"),
        "prescritor_nome": referencia.get("prescritor_nome", ""), "prescritor_registro": referencia.get("prescritor_registro", ""),
        "prescricao_situacao": referencia.get("situacao", "Sem referência registrada"),
        "conferencia_nome": referencia.get("conferida_por_nome", ""), "conferencia_em": referencia.get("conferida_em")}


def horario_brasilia(valor: str | None):
    return datetime.fromisoformat(valor).astimezone(BRASILIA).replace(tzinfo=None) if valor else None
