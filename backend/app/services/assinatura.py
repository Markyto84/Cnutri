"""Compatibilidade: novas integrações devem importar de app.modules.assinatura."""
from ..modules.assinatura import gerar_assinatura_png

__all__ = ["gerar_assinatura_png"]
