"""Valida pedidos pelo formulário vigente da unidade, antes de qualquer gravação."""
from datetime import date, datetime, timedelta, timezone
import json
import re

from fastapi import HTTPException
from sqlalchemy import select

from ..models.models import Dieta, FormularioConfig

FIXOS = {"leito", "prontuario", "nome_paciente", "dieta_id", "observacoes_alergias", "solicitante_nome"}
TIPOS = {"texto", "texto_longo", "data", "selecao", "radio", "cardapio", "selecao_dietas"}
CONTROLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validar_esquema(esquema):
    campos = esquema.get("campos") if isinstance(esquema, dict) else None
    if not isinstance(campos, list) or len(campos) > 100:
        raise HTTPException(422, "O formulário deve conter uma lista de até 100 campos")
    ids = set()
    for campo in campos:
        if not isinstance(campo, dict):
            raise HTTPException(422, "Há um campo inválido no formulário")
        chave = campo.get("id", "")
        if not isinstance(chave, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", chave) or chave in ids:
            raise HTTPException(422, "Os campos precisam de identificadores únicos com letras minúsculas, números e sublinhado")
        ids.add(chave)
        if "obrigatorio" in campo and not isinstance(campo["obrigatorio"], bool):
            raise HTTPException(422, "A obrigatoriedade dos campos deve ser verdadeira ou falsa")
        if campo.get("tipo") not in TIPOS or not isinstance(campo.get("rotulo"), str) or not campo["rotulo"].strip():
            raise HTTPException(422, "Confira o tipo e o rótulo dos campos do formulário")
        listas = [campo.get("opcoes")] if campo["tipo"] in ("selecao", "radio") else []
        if campo["tipo"] == "cardapio":
            grupos = campo.get("grupos", [])
            if not isinstance(grupos, list) or any(not isinstance(g, dict) or not isinstance(g.get("dietas"), list) for g in grupos):
                raise HTTPException(422, "Confira os grupos do cardápio")
            listas = [g.get("opcoes") for g in grupos]
        if any(not isinstance(lista, list) or len(lista) > 300 or any(not isinstance(v, str) or not v.strip() or len(v) > 2000 for v in lista) for lista in listas):
            raise HTTPException(422, "As opções devem ser listas de textos preenchidos de até 2.000 caracteres")
    return esquema


async def validar_pedido(db, filial_id, dados):
    tipo = "MEDICO" if dados.tipo_solicitacao == "MEDICO" else "ENFERMAGEM"
    config = await db.scalar(select(FormularioConfig).where(FormularioConfig.filial_id == filial_id, FormularioConfig.tipo_publico == tipo))
    if config is None:
        raise HTTPException(409, "Formulário indisponível. Solicite a configuração ao gestor")
    validar_esquema(config.esquema_json)
    campos = config.esquema_json["campos"]
    catalogo = (await db.execute(select(Dieta).where(Dieta.filial_id == filial_id, Dieta.ativa.is_(True)))).scalars().all()
    dietas = {d.id: d for d in catalogo}
    dieta = dietas.get(dados.dieta_id)
    erros = []

    def erro(chave, rotulo, mensagem):
        erros.append({"loc": ["body", chave] if chave in FIXOS else ["body", "dados_dinamicos", chave], "msg": f"{rotulo}: {mensagem}", "type": "value_error"})

    if dados.dieta_id is not None and dieta is None:
        erro("dieta_id", "Tipo de dieta", "selecione uma dieta ativa desta unidade")
    dinamicos = dados.dados_dinamicos
    if len(json.dumps(dinamicos, ensure_ascii=False).encode("utf-8")) > 65536:
        raise HTTPException(422, "Os dados do formulário excedem 64 KB")
    definidos = {campo["id"] for campo in campos}
    for chave in dinamicos:
        if chave not in definidos or chave in FIXOS:
            erro(chave[:50], "Formulário", "há campos não reconhecidos. Atualize a página antes de enviar")
    for chave in ("solicitante_identificacao", "solicitante_nome"):
        valor = getattr(dados, chave)
        if CONTROLES.search(valor) or "\n" in valor or "\r" in valor:
            erro(chave, "Registro profissional" if chave == "solicitante_identificacao" else "Solicitante", "informe um texto em uma linha")
    if dados.tipo_solicitacao == "PACIENTE" and not dados.nome_paciente:
        erro("nome_paciente", "Nome do paciente", "preenchimento obrigatório")

    for campo in campos:
        chave, tipo = campo["id"], campo["tipo"]
        rotulo = campo["rotulo"]
        valor = getattr(dados, chave, None) if chave in FIXOS else dinamicos.get(chave)
        opcoes = campo.get("opcoes", [])
        if tipo == "cardapio":
            grupo = next((g for g in campo.get("grupos", []) if dieta and dieta.nome in g.get("dietas", [])), {})
            opcoes = grupo.get("opcoes", [])
        vazio = valor is None or valor == "" or (isinstance(valor, str) and not valor.strip())
        if vazio:
            # O seletor de cardápio fica desabilitado quando a dieta não tem grupo.
            if campo.get("obrigatorio") and not (tipo == "cardapio" and not opcoes):
                erro(chave, rotulo, "preenchimento obrigatório")
            continue
        if tipo == "selecao_dietas":
            identificador = int(valor) if isinstance(valor, (str, int)) and not isinstance(valor, bool) and str(valor).isdigit() else None
            if identificador not in dietas:
                erro(chave, rotulo, "selecione uma dieta ativa desta unidade")
            continue
        if not isinstance(valor, str):
            erro(chave, rotulo, "informe um texto ou uma opção válida")
            continue
        valor = valor.strip()
        limite = 5000 if tipo == "texto_longo" else 2000 if tipo in ("selecao", "radio", "cardapio") else 1000
        if len(valor) > limite or CONTROLES.search(valor) or (tipo != "texto_longo" and ("\n" in valor or "\r" in valor)):
            erro(chave, rotulo, f"use um texto válido de até {limite} caracteres")
        if tipo in ("selecao", "radio", "cardapio") and valor not in opcoes:
            erro(chave, rotulo, "a opção não está disponível. Confira o formulário atualizado")
        if tipo == "data":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
                    raise ValueError()
                data = date.fromisoformat(valor)
                if chave == "data_nascimento" and data > datetime.now(timezone(timedelta(hours=-3))).date():
                    raise ValueError()
            except ValueError:
                erro(chave, rotulo, "informe uma data válida" if chave != "data_nascimento" else "informe uma data de nascimento válida, até hoje")
        if chave in FIXOS:
            setattr(dados, chave, valor)
        else:
            dinamicos[chave] = valor
    if erros:
        raise HTTPException(422, erros)
    return dieta
