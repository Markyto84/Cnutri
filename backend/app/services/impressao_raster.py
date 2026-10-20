"""Texto Unicode desenhado no servidor para não depender da tabela da POS80."""
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from struct import pack
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps

LARGURA_PONTOS = 576  # área de impressão de 72 mm em papel de 80 mm, 203 dpi
RESOLUCAO_DPI = 203
TAMANHO_FONTE_PT = 12
TAMANHO_FONTE_PIXELS = round(TAMANHO_FONTE_PT * RESOLUCAO_DPI / 72)
MARGEM_HORIZONTAL = 24
ALTURA_BLOCO = 128  # blocos pequenos para o buffer das impressoras térmicas
PASTA_FONTES = Path(__file__).resolve().parents[1] / "assets/fonts"


@dataclass(frozen=True)
class LinhaImpressao:
    texto: str
    centralizada: bool = False
    destaque: bool = False


@lru_cache(maxsize=2)
def _fonte(destaque: bool) -> ImageFont.FreeTypeFont:
    nome = "DejaVuSansMono-Bold.ttf" if destaque else "DejaVuSansMono.ttf"
    return ImageFont.truetype(str(PASTA_FONTES / nome), TAMANHO_FONTE_PIXELS)


def colunas_por_linha(destaque: bool = False) -> int:
    return int((LARGURA_PONTOS - 2 * MARGEM_HORIZONTAL) // _fonte(destaque).getlength("M"))


def _altura_linha(destaque: bool) -> int:
    ascendente, descendente = _fonte(destaque).getmetrics()
    return ascendente + descendente + 8


def renderizar_filipeta(linhas: Sequence[LinhaImpressao]) -> Image.Image:
    diagramadas = [
        LinhaImpressao(texto, linha.centralizada, linha.destaque)
        for linha in linhas
        for paragrafo in linha.texto.split("\n")
        for texto in (textwrap.wrap(paragrafo, colunas_por_linha(linha.destaque), break_on_hyphens=False) or [""])
    ]
    altura = 16 + sum(_altura_linha(linha.destaque) for linha in diagramadas)
    imagem = Image.new("L", (LARGURA_PONTOS, altura), 255)
    desenho = ImageDraw.Draw(imagem)
    y = 8
    for linha in diagramadas:
        fonte = _fonte(linha.destaque)
        largura = desenho.textlength(linha.texto, font=fonte)
        x = (LARGURA_PONTOS - largura) / 2 if linha.centralizada else MARGEM_HORIZONTAL
        desenho.text((x, y), linha.texto, font=fonte, fill=0, anchor="la")
        y += _altura_linha(linha.destaque)
    return imagem


def codificar_imagem(imagem: Image.Image) -> bytes:
    """GS v 0: bits 1 imprimem preto; largura em bytes e altura em pontos."""
    largura_bytes = (imagem.width + 7) // 8
    dados = bytearray(b"\x1b@\x1ba\x00")  # reset e alinhamento à esquerda
    for topo in range(0, imagem.height, ALTURA_BLOCO):
        altura = min(ALTURA_BLOCO, imagem.height - topo)
        bloco = imagem.crop((0, topo, imagem.width, topo + altura))
        pixels = ImageOps.invert(bloco.convert("L")).convert("1", dither=Image.Dither.NONE)
        dados.extend(b"\x1dv0\x00" + pack("<HH", largura_bytes, altura))
        dados.extend(pixels.tobytes())
    dados.extend(b"\n\n\x1dVB\x00")  # avanço e corte de papel
    return bytes(dados)


def rasterizar_filipeta(linhas: Sequence[LinhaImpressao]) -> bytes:
    return codificar_imagem(renderizar_filipeta(linhas))
