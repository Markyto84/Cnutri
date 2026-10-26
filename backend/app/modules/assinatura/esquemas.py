"""Contrato dos traços normalizados, independente de pedidos e entregas."""
import json
from math import hypot
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

CONTRATO = json.loads(Path(__file__).with_name("contrato.json").read_text(encoding="utf-8"))
VERSAO_CONTRATO = CONTRATO["versao"]


class PontoAssinatura(BaseModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)


class AssinaturaCreate(BaseModel):
    tracos: list[Annotated[list[PontoAssinatura], Field(min_length=CONTRATO["minPontosTraco"], max_length=CONTRATO["maxPontosTraco"])]] = Field(min_length=1, max_length=CONTRATO["maxTracos"])

    @field_validator("tracos")
    @classmethod
    def validar_desenho(cls, tracos):
        if sum(len(traco) for traco in tracos) > CONTRATO["maxPontos"]:
            raise ValueError("Assinatura muito extensa. Limpe o campo e assine novamente")
        comprimento = sum(hypot(b.x - a.x, b.y - a.y) for traco in tracos for a, b in zip(traco, traco[1:]))
        if comprimento < CONTRATO["minComprimento"]:
            raise ValueError("Desenhe a assinatura do recebedor no campo indicado")
        return tracos
