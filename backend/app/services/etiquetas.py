"""Etiquetas de 89 × 36 mm, rasterizadas para preservar acentos em ZPL e TSPL."""
from functools import lru_cache
from io import BytesIO
import textwrap
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .impressao_raster import PASTA_FONTES

LARGURA_MM = 89
ALTURA_MM = 36


def campos_etiqueta(pedido, filial):
    dinamicos = pedido.dados_dinamicos or {}

    def texto(valor):
        if isinstance(valor, (list, tuple)):
            valor = "; ".join(str(v) for v in valor)
        valor = unicodedata.normalize("NFC", str(valor if valor is not None else ""))
        return " ".join("".join(c if unicodedata.category(c) != "Cc" else " " for c in valor).split()) or "Não informado"

    return [("Unidade", texto(filial.nome)), ("Paciente", texto(pedido.nome_paciente)),
        ("Matrícula", texto(dinamicos.get("matricula"))), ("Refeição", texto(dinamicos.get("refeicao"))),
        ("Cardápio", texto(dinamicos.get("cardapio")))]


@lru_cache(maxsize=32)
def fonte_etiqueta(pixels, negrito):
    nome = "DejaVuSansMono-Bold.ttf" if negrito else "DejaVuSansMono.ttf"
    return ImageFont.truetype(str(PASTA_FONTES / nome), pixels)


def renderizar_etiqueta(campos, resolucao=203):
    if resolucao not in (203, 300):
        raise ValueError("Resolução da impressora inválida")
    largura, altura = round(LARGURA_MM * resolucao / 25.4), round(ALTURA_MM * resolucao / 25.4)
    margem = round(1.5 * resolucao / 25.4)
    for pontos in (10, 9, 8, 7):
        fonte = fonte_etiqueta(round(pontos * resolucao / 72), False)
        espaco = max(2, round(resolucao / 100))
        passo = sum(fonte.getmetrics()) + espaco
        colunas = int((largura - 2 * margem) // fonte.getlength("M"))
        linhas = [(linha, chave in ("Unidade", "Paciente")) for chave, valor in campos
            for linha in textwrap.wrap(f"{chave}: {valor}", colunas, break_on_hyphens=False)]
        if len(linhas) * passo <= altura - 2 * margem:
            imagem = Image.new("L", (largura, altura), 255)
            desenho = ImageDraw.Draw(imagem)
            for n, (linha, negrito) in enumerate(linhas):
                desenho.text((margem, margem + n * passo), linha, font=fonte_etiqueta(fonte.size, negrito), fill=0, anchor="la")
            return imagem
    raise ValueError("O texto excede a etiqueta de 89 × 36 mm. Revise o comprimento dos campos; nenhum texto será cortado")


def previa_png(campos, resolucao=203):
    arquivo = BytesIO()
    renderizar_etiqueta(campos, resolucao).save(arquivo, format="PNG")
    return arquivo.getvalue()


def codificar_etiqueta(imagem, protocolo="ZPL", intervalo_mm=2):
    largura_bytes = (imagem.width + 7) // 8
    # Padding branco até completar o último byte da linha.
    ajustada = Image.new("L", (largura_bytes * 8, imagem.height), 255)
    ajustada.paste(imagem, (0, 0))
    if protocolo == "ZPL":
        dados = ImageOps.invert(ajustada).convert("1", dither=Image.Dither.NONE).tobytes()
        cabecalho = f"^XA^PW{imagem.width}^LL{imagem.height}^LH0,0^FO0,0^GFA,{len(dados)},{len(dados)},{largura_bytes},"
        return (cabecalho + dados.hex().upper() + "^FS^PQ1,0,1,N^XZ\r\n").encode("ascii")
    if protocolo == "TSPL":
        dados = ajustada.convert("1", dither=Image.Dither.NONE).tobytes()
        cabecalho = (f"SIZE {LARGURA_MM} mm,{ALTURA_MM} mm\r\nGAP {intervalo_mm} mm,0 mm\r\n"
            f"DIRECTION 1\r\nREFERENCE 0,0\r\nCLS\r\nBITMAP 0,0,{largura_bytes},{imagem.height},0,")
        return cabecalho.encode("ascii") + dados + b"\r\nPRINT 1,1\r\n"
    raise ValueError("Protocolo da impressora de etiquetas inválido")


def montar_etiqueta(pedido, filial, configuracao):
    imagem = renderizar_etiqueta(campos_etiqueta(pedido, filial), configuracao["resolucao"])
    return codificar_etiqueta(imagem, configuracao["protocolo"], configuracao["intervalo_mm"])
