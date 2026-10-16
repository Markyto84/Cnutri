"""Impressão silenciosa de filipetas em impressoras térmicas (ESC/POS via socket TCP/IP porta 9100).

Não depende da biblioteca python-escpos: envia os bytes ESC/POS crus diretamente,
o que evita problemas de instalação de dependências no Windows.
"""
import logging
import socket

logger = logging.getLogger(__name__)

ESC = b"\x1b"
GS = b"\x1d"

LARGURA_LINHA = 42  # 80mm térmica padrão (~42 colunas)


def _centralizar(texto: str) -> bytes:
    padding = max(0, (LARGURA_LINHA - len(texto)) // 2)
    return (" " * padding + texto).encode("cp437", errors="replace") + b"\n"


def _esquerda(texto: str) -> bytes:
    return ("  " + texto)[:LARGURA_LINHA].encode("cp437", errors="replace") + b"\n"


def montar_filipeta(
    pedido_id: int,
    filial_nome: str,
    tipo_solicitacao: str,
    paciente_ou_solicitante: str,
    leito: str | None,
    dieta_nome: str | None,
    observacoes: str | None,
    severa: bool,
    andar: str | None = None,
    refeicao: str | None = None,
    para: str | None = None,
    espessado: str | None = None,
) -> bytes:
    """Monta o buffer de bytes da filipeta (modelo de bandeja)."""
    dados = b"\x1b@"  # ESC @ — reset da impressora
    dados += b"\x1b!\x30"  # fonte dupla altura/largura, negrito
    dados += _centralizar(f"PEDIDO #{pedido_id}")
    dados += b"\x1b!\x00"  # fonte normal
    dados += _centralizar(filial_nome)
    dados += _centralizar("=" * LARGURA_LINHA)

    if severa:
        dados += b"\x1b!\x38"  # negrito + duplo destaque
        dados += _centralizar("** ATENCAO: RESTRICAO SEVERA **")
        dados += b"\x1b!\x00"

    if refeicao:
        dados += _esquerda(f"Refeicao: {refeicao}")
    if para:
        dados += _esquerda(f"Para: {para}")
    if espessado:
        dados += _esquerda(f"Liquido espessado: {espessado}")
    dados += _esquerda(f"Tipo: {'MEDICO' if tipo_solicitacao == 'MEDICO' else 'PACIENTE'}")
    dados += _esquerda(f"Nome: {paciente_ou_solicitante}")
    if andar:
        dados += _esquerda(f"Andar: {andar}")
    if leito:
        dados += _esquerda(f"Leito: {leito}")
    if dieta_nome:
        dados += _esquerda(f"Dieta: {dieta_nome}")
    if observacoes:
        dados += _esquerda("Obs/Alergias:")
        for linha in observacoes.splitlines() or [observacoes]:
            dados += _esquerda(linha)
    dados += _centralizar("=" * LARGURA_LINHA)
    dados += b"\n\n"
    dados += GS + b"V\x42\x00"  # corte de papel
    return dados


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