"""Seletor Sim/Não com lista condicional, preservando opções e registros anteriores."""
from copy import deepcopy

from .formulario_paciente import normalizar_nome

CAMPO = "liquido_espessado"
TIPO = "tipo_liquido_espessado"


def formulario_liquidos(esquema):
    campos = esquema.get("campos", [])
    if not isinstance(campos, list) or any(not isinstance(c, dict) for c in campos):
        return esquema
    original = next((c for c in campos if c.get("id") == CAMPO), None)
    if original is None:
        return esquema
    filho = next((c for c in campos if c.get("id") == TIPO), None)
    opcoes = (filho or original).get("opcoes", [])
    opcoes = [v for v in opcoes if normalizar_nome(v) not in ("SIM", "NAO", "NÃO")]
    principal = {**original, "tipo": "radio", "opcoes": ["Sim", "Não"]}
    dependente = {"id": TIPO, "tipo": "selecao", "rotulo": "Líquidos disponíveis", "obrigatorio": True,
        "opcoes": opcoes, "exibir_quando": {"campo": CAMPO, "valor": "Sim"}}
    resultado = []
    for campo in campos:
        if campo.get("id") == TIPO:
            continue
        resultado.append(principal if campo.get("id") == CAMPO else campo)
        if campo.get("id") == CAMPO:
            resultado.append(dependente)
    return {**esquema, "campos": resultado}


def normalizar_liquidos(campos, dados):
    opcoes = next((c.get("opcoes", []) for c in campos if c.get("id") == TIPO), None)
    if opcoes is None:
        return dados
    resultado = dict(dados)
    valor = normalizar_nome(resultado.get(CAMPO))
    if valor in ("NAO", "NÃO"):
        resultado[CAMPO] = "Não"
        resultado.pop(TIPO, None)
    elif valor == "SIM":
        resultado[CAMPO] = "Sim"
    else:
        anterior = next((o for o in opcoes if normalizar_nome(o) == valor), None)
        if anterior is not None:
            resultado[CAMPO], resultado[TIPO] = "Sim", anterior
    return resultado


def estrutura_formulario(esquema):
    """Campos que só a TI pode alterar; a Nutrição mantém textos e listas/cardápios."""
    fixo = deepcopy(formulario_liquidos(esquema))
    for chave in ("titulo", "cabecalho"):
        fixo.pop(chave, None)
    for campo in fixo.get("campos", []):
        if campo.get("tipo") in ("selecao", "radio"):
            campo.pop("opcoes", None)
        if campo.get("tipo") == "cardapio":
            campo.pop("grupos", None)
    return fixo
