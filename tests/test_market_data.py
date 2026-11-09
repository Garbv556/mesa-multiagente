"""Cotações e métricas saem de OHLC real, sem preço semeado."""

from datetime import datetime, timezone

from src.collectors.market_data import metricas_de_serie
from src.collectors.market_sources import (
    interpretar_awesome_usdbrl,
    interpretar_cboe_vix,
    interpretar_yahoo_chart,
    montar_serie,
)
from src.finance.math_engine import calcular_atr, calcular_zscore


def _payload_yahoo(precos):
    inicio = 1_700_000_000
    timestamps = [inicio + i * 86_400 for i in range(len(precos))]
    variacao_pct = ((precos[-1] / precos[-2]) - 1.0) * 100.0
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": precos[-1],
                        "regularMarketTime": timestamps[-1] + 3_600,
                        "regularMarketChangePercent": variacao_pct,
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "high": [p + 1 for p in precos],
                                "low": [p - 1 for p in precos],
                                "close": precos,
                            }
                        ]
                    },
                }
            ]
        }
    }


def test_yahoo_e_metricas_usam_o_historico():
    precos = [100 + i for i in range(21)]
    serie = interpretar_yahoo_chart("BOVA11.SA", _payload_yahoo(precos))
    assert serie is not None
    assert serie.fonte == "yahoo"
    assert serie.preco_atual == 120
    assert serie.preco_fechamento_anterior == 119

    referencia = datetime.fromtimestamp(1_700_000_000 + 20 * 86_400 + 3_600, timezone.utc)
    assert serie.instante_mercado == referencia

    metricas = metricas_de_serie(serie, coletado_em=referencia)
    janela = [barra.close for barra in serie.barras[-20:]]
    assert metricas.zscore_20p == round(float(calcular_zscore(janela, serie.preco_atual)), 4)
    assert metricas.atr_14p == round(
        float(
            calcular_atr(
                [b.high for b in serie.barras[-20:]],
                [b.low for b in serie.barras[-20:]],
                janela,
                periodo=14,
            )
        ),
        4,
    )
    assert metricas.sparkline[-1] == 120
    assert metricas.sparkline[0] == 106
    assert len(metricas.sparkline) == 15
    assert metricas.tempo_referencia == referencia.isoformat()
    assert metricas.tempo_evento == metricas.tempo_referencia
    assert "T17:00:00" not in metricas.tempo_evento
    assert metricas.variacao_dia_pct == (120 / 119) - 1


def test_historico_curto_nao_vira_cotacao():
    assert interpretar_yahoo_chart("BOVA11.SA", _payload_yahoo([10, 11, 12])) is None
    assert montar_serie("BOVA11.SA", [], 10, datetime.now(timezone.utc), None, "yahoo") is None


def test_cboe_vix_le_o_csv_diario():
    linhas = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    for i in range(25):
        linhas.append(f"01/{i + 1:02d}/2026,{15 + i},{16 + i},{14 + i},{15.5 + i}")
    serie = interpretar_cboe_vix("\n".join(linhas))
    assert serie is not None
    assert serie.fonte == "cboe"
    assert serie.ticker == "^VIX"
    assert serie.preco_atual == 39.5
    assert serie.instante_mercado == datetime(2026, 1, 25, tzinfo=timezone.utc)


def test_awesomeapi_agrega_usdbrl():
    base = 1_700_000_000
    payload = []
    for i in range(25):
        preco = 5.0 + i * 0.01
        payload.append(
            {
                "high": preco + 0.02,
                "low": preco - 0.02,
                "bid": preco,
                "timestamp": str(base + i * 86_400),
                "pctChange": "0.20",
            }
        )
    serie = interpretar_awesome_usdbrl(payload)
    assert serie is not None
    assert serie.fonte == "awesomeapi"
    assert serie.ticker == "USDBRL=X"
    assert abs(serie.preco_atual - 5.24) < 1e-9
    assert serie.preco_fechamento_anterior < serie.preco_atual
