"""
Coletor de Dados de Mercado para a Cesta Multimercado (Opção C).
Ativos: BOVA11.SA (Ações B3), GOLD11.SA (Ouro), IVVB11.SA (S&P 500 BRL), USDBRL=X (Dólar).

Calcula em tempo real e de forma puramente determinística:
- Z-Score (normalização)
- ATR (Average True Range para posicionamento de Stop Loss)
- Retorno recente e volatilidade
Preserva os 4 tempos: Referência, Evento, Publicação e Coleta.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

from src.finance.math_engine import calcular_zscore, calcular_atr


@dataclass
class MetricasAtivo:
    ticker: str
    preco_atual: float
    preco_fechamento_anterior: float
    variacao_dia_pct: float
    zscore_20p: float
    atr_14p: float
    volatilidade_20p: float
    tempo_referencia: str
    tempo_evento: str
    tempo_publicacao: str
    tempo_coleta: str


class ColetorMercado:
    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or [
            "BOVA11.SA",
            "GOLD11.SA",
            "IVVB11.SA",
            "USDBRL=X",
        ]

    def coletar_metricas_ativo(self, ticker: str, periodo: str = "3mo") -> Optional[MetricasAtivo]:
        agora_utc = datetime.now(timezone.utc).isoformat()
        try:
            # Baixa histórico com yfinance para o ativo individual (evitando locks no sqlite)
            df = yf.download(ticker, period=periodo, interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 20:
                return None

            # Normalização de multi-index de colunas se presente
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(ticker, level=1, axis=1) if ticker in df.columns.levels[1] else df

            closes = df["Close"].dropna().values.flatten().tolist()
            highs = df["High"].dropna().values.flatten().tolist()
            lows = df["Low"].dropna().values.flatten().tolist()

            if len(closes) < 20:
                return None

            preco_atual = float(closes[-1])
            preco_anterior = float(closes[-2])
            variacao = (preco_atual / preco_anterior) - 1.0

            # Cálculos determinísticos
            zscore = calcular_zscore(closes[-20:], preco_atual)
            atr = calcular_atr(highs[-20:], lows[-20:], closes[-20:], periodo=14)

            retornos = np.diff(closes[-20:]) / closes[-20:-1]
            vol_20p = float(np.std(retornos, ddof=1))

            data_evento = str(df.index[-1].date())

            return MetricasAtivo(
                ticker=ticker,
                preco_atual=preco_atual,
                preco_fechamento_anterior=preco_anterior,
                variacao_dia_pct=variacao,
                zscore_20p=zscore,
                atr_14p=atr,
                volatilidade_20p=vol_20p,
                tempo_referencia=data_evento,
                tempo_evento=f"{data_evento}T17:00:00Z",
                tempo_publicacao=f"{data_evento}T18:00:00Z",
                tempo_coleta=agora_utc,
            )
        except Exception as e:
            print(f"[Aviso] Falha ao coletar dados para {ticker}: {e}")
            return None

    def coletar_cesta_completa(self) -> Dict[str, MetricasAtivo]:
        resultados = {}
        for t in self.tickers:
            metrica = self.coletar_metricas_ativo(t)
            if metrica:
                resultados[t] = metrica
        return resultados

    def salvar_snapshot(self, destino: str = "data/snapshots/ultimo_mercado.json") -> Path:
        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        cesta = self.coletar_cesta_completa()
        dados_serializaveis = {k: asdict(v) for k, v in cesta.items()}
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados_serializaveis, f, indent=2, ensure_ascii=False)
        return caminho


if __name__ == "__main__":
    coletor = ColetorMercado()
    print("Coletando métricas determinísticas para a cesta multimercado...")
    snapshot = coletor.salvar_snapshot()
    print(f"Snapshot gravado com sucesso em: {snapshot}")
