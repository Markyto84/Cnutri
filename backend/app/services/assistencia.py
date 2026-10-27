"""Referência externa e evidências operacionais; não emite prescrição clínica."""
from fastapi import HTTPException

from ..models.models import EventoAssistencial
from .formulario_paciente import ACOMPANHANTE, normalizar_nome

CAMPOS_PEDIDO = ("tipo_solicitacao", "solicitante_identificacao", "solicitante_nome", "leito", "prontuario",
    "nome_paciente", "dieta_id", "observacoes_alergias", "dados_dinamicos")


def aceita_referencia_anterior(dados):
    return dados.tipo_solicitacao == "PACIENTE" and normalizar_nome((dados.dados_dinamicos or {}).get("para")) != ACOMPANHANTE


def validar_referencia(dados):
    # A referência saiu dos formulários; somente clientes anteriores ainda a enviam.
    if not aceita_referencia_anterior(dados) and dados.prescricao is not None:
        raise HTTPException(422, "A referência clínica é destinada somente às refeições de pacientes")


def referencia_informada(dados):
    return {**dados.prescricao.model_dump(mode="json"), "situacao": "INFORMADA"} if dados.prescricao else None


def retrato(pedido):
    dieta = pedido.__dict__.get("dieta")
    return {**{c: getattr(pedido, c) for c in CAMPOS_PEDIDO}, "status": pedido.status,
        "prescricao": pedido.prescricao, "versao": pedido.versao or 1,
        "dieta_nome": dieta.nome if dieta else None}


def registrar_evento(db, pedido, acao, usuario=None, antes=None, depois=None, motivo=None):
    db.add(EventoAssistencial(pedido_id=pedido.id, acao=acao,
        autor_usuario_id=usuario.id if usuario else None, autor_nome=usuario.nome if usuario else None,
        autor_perfil=usuario.perfil.nome if usuario else None,
        motivo=motivo, antes=antes, depois=depois))


def registrar_etapa(db, pedido, usuario, anterior, novo, motivo=None):
    registrar_evento(db, pedido, "ETAPA_ALTERADA", usuario, {"status": anterior}, {"status": novo}, motivo)
