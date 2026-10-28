"""Dados dos dashboards e regras compartilhadas das etapas da cozinha."""
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException

STATUS_ATIVOS = ("PENDENTE", "EM_PREPARO", "PRONTO")


def validar_transicao_cozinha(anterior: str, novo: str) -> None:
    """Mesma sequência nas rotas públicas, autenticadas e de clientes anteriores."""
    if anterior not in STATUS_ATIVOS:
        raise HTTPException(409, "Este pedido já foi entregue ou cancelado")
    if anterior == novo:
        return
    seguinte = {"PENDENTE": "EM_PREPARO", "EM_PREPARO": "PRONTO"}.get(anterior)
    if novo not in (seguinte, "CANCELADO"):
        raise HTTPException(409, "A etapa do pedido mudou. Atualize o painel")


CAMPOS_OPERACIONAIS = frozenset({
    "andar", "internado_mais_6h", "refeicao", "para", "cardapio", "cardapio_acompanhante", "liquido_espessado", "tipo_liquido_espessado",
    "equipe", "horario_entrega", "suco", "sobremesa", "local_entrega",
})


def data_utc(valor) -> str | None:
    if not valor:
        return None
    data = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
    return data.replace(tzinfo=timezone.utc).isoformat() if data.tzinfo is None else data.isoformat()


def pedido_operacional(dados: dict, autenticado=False) -> dict:
    if not autenticado:
        # Sem nomes, localização, dieta, alergias, metadados de impressão ou campos futuros.
        return {"id": dados["id"], "filial_id": dados["filial_id"], "tipo_solicitacao": dados["tipo_solicitacao"],
            "status": dados["status"], "criado_em": data_utc(dados.get("criado_em")),
            "concluido_em": data_utc(dados.get("concluido_em")), "dados_restritos": True,
            **({"em_entrega": True} if dados.get("retirada") else {})}
    dinamicos = dados.get("dados_dinamicos") or {}
    idade = None
    try:
        nascimento = date.fromisoformat(dinamicos.get("data_nascimento", ""))
        hoje = datetime.now(timezone(timedelta(hours=-3))).date()
        calculada = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        if 0 <= calculada < 130:
            idade = calculada
    except (ValueError, TypeError):
        pass
    dieta = dados.get("dieta")
    return {
        "id": dados["id"], "filial_id": dados["filial_id"], "tipo_solicitacao": dados["tipo_solicitacao"],
        "nome_paciente": dados.get("nome_paciente"), "solicitante_nome": dados.get("solicitante_nome"),
        "leito": dados.get("leito"), "idade": idade,
        "dieta": {k: dieta[k] for k in ("id", "nome", "severa")} if dieta else None,
        "observacoes_alergias": dados.get("observacoes_alergias"),
        "dados_dinamicos": {k: v for k, v in dinamicos.items() if k in CAMPOS_OPERACIONAIS},
        "status": dados["status"], "criado_em": data_utc(dados.get("criado_em")),
        "concluido_em": data_utc(dados.get("concluido_em")),
        "impressao": dados.get("impressao"),
        "etiqueta": dados.get("etiqueta"),
        "versao": dados.get("versao", 1),
        "recebimento_qr": dados.get("recebimento_qr", False),
        "retirada": {**dados["retirada"], "retirada_em": data_utc(dados["retirada"]["retirada_em"])} if dados.get("retirada") else None,
    }
