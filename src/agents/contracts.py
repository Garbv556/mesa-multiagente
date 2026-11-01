"""
Contratos estritamente tipados para a equipe mínima de agentes.
Garante que a comunicação entre Analista, Revisor e o OrderGate não contenha texto livre ambíguo.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ViesDirecional(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class ParecerRevisao(str, Enum):
    APROVADO = "APROVADO"
    REJEITADO = "REJEITADO"
    DADOS_INSUFICIENTES = "DADOS_INSUFICIENTES"


class PropostaAnalista(BaseModel):
    ativo: str = Field(description="Ticker do ativo (ex: BOVA11.SA, GOLD11.SA)")
    tipo_operacao: str = Field(description="'COMPRA' ou 'VENDA'")
    preco_referencia: float
    preco_stop_loss: float
    preco_take_profit: float
    probabilidade_estimada: float = Field(ge=0.0, le=1.0, description="Probabilidade calibrada [0.0 a 1.0]")
    justificativa_quant: str = Field(description="Resumo do sinal matemático (ex: Z-Score esticado, ATR)")
    vies_macro: ViesDirecional


class DiagnosticoMercado(BaseModel):
    regime_macro_vigente: str = Field(description="Goldilocks, Reflação, Estagflação ou Desinflação")
    resumo_cenario: str
    propostas: List[PropostaAnalista] = Field(default_factory=list)
    timestamp_geracao: str


class RelatorioRevisao(BaseModel):
    parecer: ParecerRevisao
    contrapontos_identificados: List[str]
    inconsistencias_temporais: List[str]
    auditoria_matematica_valida: bool
    justificativa_final: str
