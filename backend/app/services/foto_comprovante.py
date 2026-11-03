"""Normaliza a fotografia sem guardar o original, EXIF ou cópias em Base64."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_FOTO_BYTES = 300 * 1024
MAX_PIXELS = 32_000_000
MAX_LADO = 2000
FORMATOS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True)
class FotoComprovante:
    dados: bytes
    largura: int
    altura: int

    @property
    def sha256(self):
        return sha256(self.dados).hexdigest()


def otimizar_foto(dados: bytes) -> FotoComprovante:
    if not dados or len(dados) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "A foto deve ter no máximo 12 MB. Aproxime a câmera da filipeta e tente novamente")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(dados)) as original:
                if original.format not in FORMATOS or getattr(original, "n_frames", 1) != 1:
                    raise HTTPException(422, "Envie uma fotografia JPG, PNG ou WebP, sem animação")
                if original.width * original.height > MAX_PIXELS:
                    raise HTTPException(413, "A resolução da foto é muito alta. Use uma foto de até 32 megapixels")
                if min(original.size) < 240 or max(original.size) < 600:
                    raise HTTPException(422, "A foto é pequena demais para leitura. Fotografe a filipeta novamente")
                original.load()
                orientada = ImageOps.exif_transpose(original)
                # O papel é monocromático. Fundo branco preserva imagens com transparência.
                if orientada.mode in ("RGBA", "LA") or "transparency" in orientada.info:
                    rgba = orientada.convert("RGBA")
                    branca = Image.new("RGB", rgba.size, "white")
                    branca.paste(rgba, mask=rgba.getchannel("A"))
                    orientada = branca
                imagem = orientada.convert("L")
                imagem.thumbnail((MAX_LADO, MAX_LADO), Image.Resampling.LANCZOS)
                # Mantém pelo menos 1600 px nas fotos grandes, sem reduzir a qualidade abaixo de 72.
                for limite in (2000, 1800, 1600):
                    candidata = imagem.copy()
                    candidata.thumbnail((limite, limite), Image.Resampling.LANCZOS)
                    for qualidade in (86, 82, 78, 75, 72):
                        saida = BytesIO()
                        candidata.save(saida, format="JPEG", quality=qualidade, optimize=True, progressive=True)
                        if saida.tell() <= MAX_FOTO_BYTES:
                            return FotoComprovante(saida.getvalue(), *candidata.size)
                raise HTTPException(422, "A foto contém detalhes demais para compactar com nitidez. Enquadre somente a filipeta, com boa luz")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Não foi possível ler a foto. Use JPG, PNG ou WebP e fotografe novamente") from None
