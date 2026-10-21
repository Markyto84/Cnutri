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
from fastapi.concurrency import run_in_threadpool

from ..models.models import Dieta, Filial, FormularioConfig, Pedido
from .impressao_raster import LinhaImpressao, colunas_por_linha, rasterizar_filipeta

logger = logging.getLogger(__name__)

LARGURA_LINHA = colunas_por_linha()  # calculada para a fonte e a área útil do papel
# Permanecem no formulário e no pedido; são omitidos somente no papel.
CAMPOS_OCULTOS_FILIPETA = frozenset({"sexo", "prontuario"})

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
        if chave in CAMPOS_OCULTOS_FILIPETA:
            continue
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


def compor_linhas_filipeta(
    pedido: Pedido,
    filial_nome: str,
    esquema_json: dict | None = None,
    dieta_nome: str | None = None,
    severa: bool = False,
) -> list[LinhaImpressao]:
    """Dados operacionais e comprovante de recebimento, sem truncar os textos."""
    linhas = []

    def adicionar(texto: str, centralizada: bool = False, destaque: bool = False):
        largura = colunas_por_linha(destaque)
        linhas.extend(LinhaImpressao(linha, centralizada, destaque) for linha in _linhas(texto, largura))

    adicionar(f"PEDIDO #{pedido.id}", centralizada=True, destaque=True)
    adicionar(filial_nome, centralizada=True)
    adicionar("=" * LARGURA_LINHA, centralizada=True)

    if severa:
        adicionar("ATENÇÃO:\nRESTRIÇÃO SEVERA", centralizada=True, destaque=True)

    adicionar(f"Tipo: {'MÉDICO' if pedido.tipo_solicitacao == 'MEDICO' else 'PACIENTE'}")
    for rotulo, valor in _campos_filipeta(pedido, dieta_nome, esquema_json):
        adicionar(f"{rotulo}: {valor}")
    adicionar("=" * LARGURA_LINHA, centralizada=True)
    adicionar("ENTREGA À RECEPÇÃO", centralizada=True, destaque=True)
    adicionar("Assinatura:")
    adicionar("\n\n")  # espaço para assinar à mão antes da linha
    adicionar("_" * LARGURA_LINHA)
    adicionar("")
    adicionar("Data e hora:")
    adicionar("")
    adicionar("____/____/________  ____:____")
    adicionar("")
    adicionar("=" * LARGURA_LINHA, centralizada=True)
    return linhas


def montar_filipeta(
    pedido: Pedido,
    filial_nome: str,
    esquema_json: dict | None = None,
    dieta_nome: str | None = None,
    severa: bool = False,
) -> bytes:
    """Envia letras já desenhadas, preservando acentos sem usar code pages."""
    return rasterizar_filipeta(compor_linhas_filipeta(pedido, filial_nome, esquema_json, dieta_nome, severa))


async def montar_filipeta_configurada(
    db: AsyncSession, pedido: Pedido, filial: Filial, dieta: Dieta | None,
) -> bytes:
    """Usado tanto no envio automático quanto na reimpressão da cozinha."""
    tipo_publico = "MEDICO" if pedido.tipo_solicitacao == "MEDICO" else "ENFERMAGEM"
    config = (await db.execute(select(FormularioConfig).where(
        FormularioConfig.filial_id == pedido.filial_id,
        FormularioConfig.tipo_publico == tipo_publico,
    ))).scalar_one_or_none()
    return await run_in_threadpool(montar_filipeta,
        pedido=pedido,
        filial_nome=filial.nome,
        esquema_json=config.esquema_json if config else None,
        dieta_nome=dieta.nome if dieta else None,
        severa=bool(dieta.severa) if dieta else False,
    )


class ErroEnvioImpressora(Exception):
    def __init__(self, incerto=False):
        self.incerto = incerto
        super().__init__("O envio à impressora não foi concluído")


def enviar_filipeta(ip: str, dados: bytes, porta: int = 9100, timeout: float = 3.0):
    """Confirma somente o envio TCP; falha após conectar pode ter enviado parte do papel."""
    try:
        sock = socket.create_connection((ip, porta), timeout=timeout)
    except OSError:
        raise ErroEnvioImpressora(incerto=False) from None
    try:
        with sock:
            sock.sendall(dados)
    except OSError:
        raise ErroEnvioImpressora(incerto=True) from None


def imprimir_filipeta(ip: str, dados: bytes, porta: int = 9100, timeout: float = 3.0) -> bool:
    """Compatibilidade: True significa dados enviados, sem confirmação física de papel."""
    try:
        enviar_filipeta(ip, dados, porta, timeout)
        return True
    except ErroEnvioImpressora:
        logger.warning("Envio da filipeta não concluído")
        return False
