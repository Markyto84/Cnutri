"""Converte somente os traços validados em um comprovante PNG, sem arquivos enviados."""
from io import BytesIO

from PIL import Image, ImageDraw

from ..schemas.schemas import AssinaturaCreate


def gerar_assinatura_png(assinatura: AssinaturaCreate) -> bytes:
    imagem = Image.new("L", (1000, 500), 255)
    desenho = ImageDraw.Draw(imagem)
    for traco in assinatura.tracos:
        pontos = [(round(p.x * 999), round(p.y * 499)) for p in traco]
        desenho.line(pontos, fill=20, width=6, joint="curve")
        for x, y in (pontos[0], pontos[-1]):
            desenho.ellipse((x - 3, y - 3, x + 3, y + 3), fill=20)
    arquivo = BytesIO()
    imagem.save(arquivo, format="PNG")
    return arquivo.getvalue()
