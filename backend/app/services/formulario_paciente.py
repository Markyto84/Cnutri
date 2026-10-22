"""Regras do destinatário sem duplicar o cadastro de cardápios da unidade."""
import unicodedata

ACOMPANHANTE = "ACOMPANHANTE"
AMBOS = "PACIENTE E ACOMPANHANTE"
CARDAPIO_ACOMPANHANTE = "cardapio_acompanhante"


def normalizar_nome(valor):
    return unicodedata.normalize("NFC", valor).strip().upper() if isinstance(valor, str) else ""


def formulario_paciente(esquema):
    campos = esquema.get("campos", [])
    por_id = {c["id"]: c for c in campos}
    cardapio = por_id.get("cardapio", {})
    if "para" not in por_id or por_id.get("dieta_id", {}).get("tipo") != "selecao_dietas" or cardapio.get("tipo") != "cardapio":
        return esquema
    # O campo derivado sempre lê os grupos atuais do cardápio principal.
    acompanhante = {"id": CARDAPIO_ACOMPANHANTE, "tipo": "cardapio", "rotulo": "Cardápio do acompanhante",
        "obrigatorio": True, "grupos": cardapio.get("grupos", []), "dieta_fixa": "GERAL",
        "exibir_quando": {"campo": "para", "valor": AMBOS}}
    resultado = []
    for campo in campos:
        if campo["id"] == CARDAPIO_ACOMPANHANTE:
            continue
        resultado.append(campo)
        if campo["id"] == "cardapio":
            resultado.append(acompanhante)
    return {**esquema, "campos": resultado, "regras_acompanhante": True}


def campo_visivel(campo, valores):
    condicao = campo.get("exibir_quando")
    return not condicao or normalizar_nome(valores.get(condicao["campo"])) == normalizar_nome(condicao["valor"])


def opcoes_cardapio(campo, dieta_nome):
    nome = normalizar_nome(campo.get("dieta_fixa", dieta_nome))
    grupo = next((g for g in campo.get("grupos", []) if nome and any(normalizar_nome(d) == nome for d in g.get("dietas", []))), {})
    return grupo.get("opcoes", [])
