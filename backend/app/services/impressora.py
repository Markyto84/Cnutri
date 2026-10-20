"""Impressão silenciosa de filipetas em impressoras térmicas (ESC/POS via socket TCP/IP porta 9100).

Não depende da biblioteca python-escpos: envia os bytes ESC/POS crus diretamente,
o que evita problemas de instalação de dependências no Windows.
"""
import logging
import socket
import textwrap
import unicodedata
from datetime import date
from collections.abc import Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Dieta, Filial, FormularioConfig, Pedido

logger = logging.getLogger(__name__)

ESC = b"\x1b"
GS = b"\x1d"

LARGURA_LINHA = 42  # 80mm térmica padrão (~42 colunas)
CODIFICACAO = "cp850"

ROTULOS_PADRAO = {
    "solicitante_nome": "Solicitante",
    "solicitante_identificacao": "Registro profissional",
    "leito": "Leito",
    "andar": "Andar / Setor",
    "internado_mais_6h": "Internado mais que 06 horas?",
    "prontuario": "Prontuário",
    "nome_paciente": "Nome do Paciente",
    "matricula": "Matrícula",
    "data_nascimento": "Data de Nascimento",
    "sexo": "Sexo",
    "equipe": "Equipe",
    "horario_entrega": "Horário de entrega",
    "refeicao": "Refeição",
    "para": "Para",
    "dieta_id": "Tipo de Dieta",
    "cardapio": "Cardápio",
    "liquido_espessado": "Líquido espessado",
    "suco": "Suco",
    "sobremesa": "Sobremesa",
    "local_entrega": "Local de entrega",
    "observacoes_alergias": "Restrições / Alergias / Observações",
}


def _linhas(texto: str, largura: int) -> list[str]:
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    # Dados dos formulários não podem executar comandos ESC/POS.
    texto = "".join(c for c in texto if c == "\n" or unicodedata.category(c) != "Cc")
    texto = texto.translate(str.maketrans({"—": "-", "–": "-", "“": '"', "”": '"', "’": "'"}))
    linhas = []
    for paragrafo in texto.split("\n"):
        linhas.extend(textwrap.wrap(paragrafo, largura, break_on_hyphens=False) or [""])
    return linhas


def _centralizar(texto: str, largura: int = LARGURA_LINHA) -> bytes:
    return b"".join(
        (" " * max(0, (largura - len(linha)) // 2) + linha + "\n").encode(CODIFICACAO, errors="replace")
        for linha in _linhas(texto, largura)
    )


def _esquerda(texto: str) -> bytes:
    return b"".join(
        ("  " + linha + "\n").encode(CODIFICACAO, errors="replace")
        for linha in _linhas(texto, LARGURA_LINHA - 2)
    )


def _preenchido(valor: Any) -> bool:
    return valor is not None and valor != "" and valor != [] and valor != {}


def _formatar_valor(valor: Any, tipo: str | None = None) -> str:
    if not _preenchido(valor) or isinstance(valor, str) and not valor.strip():
        return "Não informado"
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, dict):
        return "\n".join(f"{chave}: {_formatar_valor(item)}" for chave, item in valor.items())
    if isinstance(valor, list):
        return "; ".join(_formatar_valor(item) for item in valor)
    if tipo == "data":
        try:
            return date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
        except ValueError:
            pass  # Um valor antigo fora do padrão continua visível.
    return str(valor)


def _campos_filipeta(
    pedido: Pedido, dieta_nome: str | None, esquema_json: dict | None,
) -> Iterator[tuple[str, str]]:
    valores = {
        **(pedido.dados_dinamicos or {}),
        "solicitante_nome": pedido.solicitante_nome,
        "solicitante_identificacao": pedido.solicitante_identificacao,
        "leito": pedido.leito,
        "prontuario": pedido.prontuario,
        "nome_paciente": pedido.nome_paciente,
        "dieta_id": dieta_nome or (f"ID {pedido.dieta_id}" if pedido.dieta_id is not None else None),
        "observacoes_alergias": pedido.observacoes_alergias,
    }
    campos = {
        campo["id"]: campo
        for campo in (esquema_json or {}).get("campos", [])
        if isinstance(campo, dict) and isinstance(campo.get("id"), str)
    }
    ordem = dict.fromkeys([
        "solicitante_nome", "solicitante_identificacao", *campos, *ROTULOS_PADRAO, *valores,
    ])
    for chave in ordem:
        valor = valores.get(chave)
        if (
            chave not in campos
            and chave not in ("solicitante_nome", "solicitante_identificacao")
            and not _preenchido(valor)
        ):
            continue
        campo = campos.get(chave, {})
        rotulo = campo.get("rotulo") or ROTULOS_PADRAO.get(chave) or chave.replace("_", " ").capitalize()
        tipo = campo.get("tipo") or ("data" if chave == "data_nascimento" else None)
        yield rotulo, _formatar_valor(valor, tipo)


def montar_filipeta(
    pedido: Pedido,
    filial_nome: str,
    esquema_json: dict | None = None,
    dieta_nome: str | None = None,
    severa: bool = False,
) -> bytes:
    """Imprime todos os campos, na ordem do formulário, sem cortar seus valores."""
    dados = ESC + b"@"  # reset da impressora
    # ESC t 2: PC850 (multilíngue), com os acentos usados em português.
    dados += ESC + b"t\x02"
    dados += ESC + b"!\x38"  # negrito, dupla altura/largura
    dados += _centralizar(f"PEDIDO #{pedido.id}", LARGURA_LINHA // 2)
    dados += ESC + b"!\x00"  # fonte normal
    dados += _centralizar(filial_nome)
    dados += _centralizar("=" * LARGURA_LINHA)

    if severa:
        dados += ESC + b"!\x38"
        dados += _centralizar("ATENÇÃO:\nRESTRIÇÃO SEVERA", LARGURA_LINHA // 2)
        dados += ESC + b"!\x00"

    dados += _esquerda(f"Tipo: {'MÉDICO' if pedido.tipo_solicitacao == 'MEDICO' else 'PACIENTE'}")
    for rotulo, valor in _campos_filipeta(pedido, dieta_nome, esquema_json):
        dados += _esquerda(f"{rotulo}: {valor}")
    dados += _centralizar("=" * LARGURA_LINHA)
    dados += b"\n\n"
    dados += GS + b"V\x42\x00"  # corte de papel
    return dados


async def montar_filipeta_configurada(
    db: AsyncSession, pedido: Pedido, filial: Filial, dieta: Dieta | None,
) -> bytes:
    """Usado tanto no envio automático quanto na reimpressão da cozinha."""
    tipo_publico = "MEDICO" if pedido.tipo_solicitacao == "MEDICO" else "ENFERMAGEM"
    config = (await db.execute(select(FormularioConfig).where(
        FormularioConfig.filial_id == pedido.filial_id,
        FormularioConfig.tipo_publico == tipo_publico,
    ))).scalar_one_or_none()
    return montar_filipeta(
        pedido=pedido,
        filial_nome=filial.nome,
        esquema_json=config.esquema_json if config else None,
        dieta_nome=dieta.nome if dieta else None,
        severa=bool(dieta.severa) if dieta else False,
    )


def imprimir_filipeta(ip: str, dados: bytes, porta: int = 9100, timeout: float = 3.0) -> bool:
    """Envia os bytes ESC/POS à impressora térmica. Retorna True se imprimiu."""
    try:
        with socket.create_connection((ip, porta), timeout=timeout) as sock:
            sock.sendall(dados)
        logger.info("Filipeta enviada para %s:%s", ip, porta)
        return True
    except Exception as exc:  # impressora offline / IP errado → não trava o pedido
        logger.warning("Falha ao imprimir em %s:%s — %s", ip, porta, exc)
        return False
