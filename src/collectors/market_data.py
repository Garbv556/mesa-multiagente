"""
Coletor de dados reais da cesta multimercado.

Ativos: BOVA11.SA, IVVB11.SA, GOLD11.SA, USDBRL=X e ^VIX.

Preço, variação, Z-Score (20 pregões), ATR (14), volatilidade (20) e sparkline
saem do OHLC diário devolvido por uma fonte real. O horário de referência é o
carimbo do negócio (ou do candle diário) nessa fonte. Se nenhuma fonte entregar
histórico suficiente, o ativo fica de fora da cesta — o coletor não completa
com preço sintético.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import warnings

import numpy as np

from src.collectors.market_sources import (
    FONTES_REAIS,
    SerieMercado,
    provedores_para,
)
from src.finance.math_engine import calcular_atr, calcular_zscore

warnings.filterwarnings("ignore")


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
    nome: str = ""
    categoria: str = "B3"
    variacao_nominal: float = 0.0
    sparkline: Optional[List[float]] = None
    fonte: str = ""
    disponivel: bool = True
    dados_stale: bool = False
    aviso: Optional[str] = None


METADADOS_ATIVOS: Dict[str, Dict[str, str]] = {
    "BOVA11.SA": {"nome": "iShares Ibovespa", "categoria": "B3"},
    "IVVB11.SA": {"nome": "iShares S&P 500", "categoria": "Global"},
    "GOLD11.SA": {"nome": "Trend Ouro B3", "categoria": "Hedge"},
    "USDBRL=X": {"nome": "Dólar Comercial", "categoria": "Moeda"},
    "^VIX": {"nome": "CBOE Volatilidade", "categoria": "Macro"},
}

TICKERS_CESTA: List[str] = list(METADADOS_ATIVOS.keys())


def _casas_decimais(ticker: str) -> int:
    return 4 if ticker == "USDBRL=X" else 2


def metricas_de_serie(serie: SerieMercado, coletado_em: Optional[datetime] = None) -> MetricasAtivo:
    """Calcula as métricas da API a partir de uma série real já validada."""
    if serie.fonte not in FONTES_REAIS:
        raise ValueError(f"Fonte desconhecida para {serie.ticker}: {serie.fonte}")

    janela = list(serie.barras[-20:])
    if len(janela) < 20:
        raise ValueError(f"Histórico insuficiente para {serie.ticker}.")

    closes = [barra.close for barra in janela]
    highs = [barra.high for barra in janela]
    lows = [barra.low for barra in janela]
    zscore = float(calcular_zscore(closes, serie.preco_atual))
    atr = float(calcular_atr(highs, lows, closes, periodo=14))
    retornos = np.diff(closes) / np.asarray(closes[:-1], dtype=float)
    volatilidade = float(np.std(retornos, ddof=1))

    casas = _casas_decimais(serie.ticker)
    preco = round(float(serie.preco_atual), casas)
    anterior = round(float(serie.preco_fechamento_anterior), casas)
    if anterior <= 0:
        raise ValueError(f"Fechamento anterior inválido para {serie.ticker}.")

    agora = (coletado_em or datetime.now(timezone.utc)).astimezone(timezone.utc)
    carimbo_mercado = serie.instante_mercado.astimezone(timezone.utc).isoformat()
    meta = METADADOS_ATIVOS.get(serie.ticker, {"nome": serie.ticker, "categoria": "B3"})
    sparkline = [round(float(barra.close), casas) for barra in serie.barras[-15:]]
    if sparkline:
        sparkline[-1] = preco

    return MetricasAtivo(
        ticker=serie.ticker,
        preco_atual=preco,
        preco_fechamento_anterior=anterior,
        variacao_dia_pct=(preco / anterior) - 1.0,
        zscore_20p=round(zscore, 4),
        atr_14p=round(atr, 4),
        volatilidade_20p=round(volatilidade, 6),
        tempo_referencia=carimbo_mercado,
        tempo_evento=carimbo_mercado,
        tempo_publicacao=carimbo_mercado,
        tempo_coleta=agora.isoformat(),
        nome=meta["nome"],
        categoria=meta["categoria"],
        variacao_nominal=round(preco - anterior, casas),
        sparkline=sparkline,
        fonte=serie.fonte,
        disponivel=True,
        dados_stale=False,
        aviso=None,
    )


class ColetorMercado:
    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = list(tickers or TICKERS_CESTA)
        self.erros: Dict[str, str] = {}

    def coletar_metricas_ativo(self, ticker: str, periodo: str = "6mo") -> Optional[MetricasAtivo]:
        """
        Tenta as fontes reais na ordem definida em `provedores_para`.

        `periodo` permanece na assinatura por compatibilidade; cada fonte pede
        seis meses, o bastante para Z-Score 20 e ATR 14.
        """
        del periodo  # a janela mínima é garantida pelas fontes (6 meses / 90 dias)
        erros: List[str] = []
        for nome, buscar in provedores_para(ticker):
            try:
                serie = buscar(ticker)
            except Exception as exc:  # noqa: BLE001 - registra e segue para a reserva
                erros.append(f"{nome}: {exc}")
                continue
            if serie is None:
                erros.append(f"{nome}: sem histórico suficiente")
                continue
            try:
                return metricas_de_serie(serie)
            except Exception as exc:  # noqa: BLE001
                erros.append(f"{nome}: {exc}")
        self.erros[ticker] = " | ".join(erros)[:240] if erros else "nenhuma fonte configurada"
        print(f"[Aviso] Falha ao coletar dados reais para {ticker}: {self.erros[ticker]}")
        return None

    def coletar_cesta_completa(self) -> Dict[str, MetricasAtivo]:
        self.erros = {}
        resultados: Dict[str, MetricasAtivo] = {}
        for ticker in self.tickers:
            metrica = self.coletar_metricas_ativo(ticker)
            if metrica is not None:
                resultados[ticker] = metrica
        return resultados

    def salvar_snapshot(
        self,
        destino: str = "data/snapshots/ultimo_mercado.json",
        cesta: Optional[Dict[str, MetricasAtivo]] = None,
    ) -> Path:
        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if cesta is None:
            cesta = self.coletar_cesta_completa()

        existente: Dict[str, Any] = {}
        if caminho.exists():
            try:
                bruto = json.loads(caminho.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                bruto = {}
            if isinstance(bruto, dict):
                existente = {
                    ticker: item
                    for ticker, item in bruto.items()
                    if isinstance(item, dict) and item.get("fonte") in FONTES_REAIS
                }

        for ticker, metrica in (cesta or {}).items():
            item = asdict(metrica) if hasattr(metrica, "__dataclass_fields__") else dict(metrica)
            if item.get("fonte") not in FONTES_REAIS or not item.get("preco_atual"):
                continue
            existente[ticker] = item
        if existente:
            caminho.write_text(json.dumps(existente, indent=2, ensure_ascii=False), encoding="utf-8")
        return caminho


if __name__ == "__main__":
    coletor = ColetorMercado()
    print("Coletando cotações reais da cesta multimercado...")
    snapshot = coletor.salvar_snapshot()
    print(f"Snapshot gravado em: {snapshot}")
    if coletor.erros:
        print(f"Falhas: {coletor.erros}")
