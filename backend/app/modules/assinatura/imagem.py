"""Geração de PNG em memória a partir do contrato de assinatura validado."""
from io import BytesIO

from PIL import Image, ImageDraw

from .esquemas import AssinaturaCreate, CONTRATO


def gerar_assinatura_png(assinatura: AssinaturaCreate | dict) -> bytes:
    if not isinstance(assinatura, AssinaturaCreate):
        assinatura = AssinaturaCreate.model_validate(assinatura)
    largura, altura, espessura = CONTRATO["largura"], CONTRATO["altura"], CONTRATO["espessura"]
    imagem = Image.new("L", (largura, altura), 255)
    desenho = ImageDraw.Draw(imagem)
    raio = espessura // 2
    for traco in assinatura.tracos:
        pontos = [(round(p.x * (largura - 1)), round(p.y * (altura - 1))) for p in traco]
        desenho.line(pontos, fill=20, width=espessura, joint="curve")
        for x, y in (pontos[0], pontos[-1]):
            desenho.ellipse((x - raio, y - raio, x + raio, y + raio), fill=20)
    arquivo = BytesIO()
    imagem.save(arquivo, format="PNG")
    return arquivo.getvalue()
