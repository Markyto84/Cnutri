"""Retratos explícitos de configuração; nunca serialize payloads de credenciais."""
from copy import deepcopy

from ..models.models import AuditoriaAdministrativa

UNIDADE = ("nome", "codigo_slug", "ip_impressora", "ativa")
DIETA = ("nome", "descricao", "severa", "ativa")
FORMULARIO = ("tipo_publico", "esquema_json")
ETIQUETA = ("modelo", "ip", "porta", "protocolo", "resolucao", "intervalo_mm")


def retrato(objeto, campos):
    return {campo: deepcopy(getattr(objeto, campo)) for campo in campos}


def retrato_usuario(usuario):
    return {**retrato(usuario, ("nome", "nome_usuario", "ativo", "origem_autenticacao", "usuario_ad",
                               "troca_senha_obrigatoria")),
            "perfil": usuario.perfil.nome, "filial_ids": sorted(f.id for f in usuario.filiais)}


def registrar(db, autor, entidade, entidade_id, filial_id, antes, depois, acao="ALTERAR"):
    # Só os campos modificados são persistidos. Chamador usa retratos de campos permitidos.
    if antes == depois:
        return
    if antes is not None and depois is not None:
        chaves = {k for k in antes.keys() | depois.keys() if antes.get(k) != depois.get(k)}
        antes = {k: antes.get(k) for k in sorted(chaves)}
        depois = {k: depois.get(k) for k in sorted(chaves)}
    db.add(AuditoriaAdministrativa(autor_usuario_id=autor.id, autor_nome=autor.nome,
        entidade=entidade, entidade_id=entidade_id, filial_id=filial_id, acao=acao,
        antes=deepcopy(antes), depois=deepcopy(depois)))
