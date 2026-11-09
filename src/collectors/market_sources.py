"""
Fontes reais de OHLC diário para a cesta da mesa.

Nenhuma função deste módulo inventa preço, variação ou candle. Se a resposta
da fonte vier vazia ou curta demais para as métricas, o retorno é None.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from typing import List, Optional, Sequence
from urllib.parse import quote

import requests


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,text/plain,*/*",
}

FONTES_REAIS = frozenset({"yahoo", "yfinance", "brapi", "cboe", "awesomeapi"})

BRAPI_SIMBOLOS = {
    "BOVA11.SA": "BOVA11",
    "IVVB11.SA": "IVVB11",
    "GOLD11.SA": "GOLD11",
}

TIMEOUT_SEGUNDOS = 12
MINIMO_BARRAS = 20


@dataclass(frozen=True)
class BarraOHLC:
    instante: datetime
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SerieMercado:
    ticker: str
    preco_atual: float
    preco_fechamento_anterior: float
    variacao_dia_pct: float
    instante_mercado: datetime
    barras: Sequence[BarraOHLC]
    fonte: str


def montar_serie(
    ticker: str,
    barras: Sequence[BarraOHLC],
    preco_atual: float,
    instante_mercado: datetime,
    variacao_percentual: Optional[float],
    fonte: str,
) -> Optional[SerieMercado]:
    """
    Fecha a série com o último preço observado.

    A variação oficial da fonte só entra quando o fechamento anterior
    implícito concorda com o candle anterior (tolerância de 0,5%).
    Fora disso, a variação sai dos dois últimos fechamentos reais.
    """
    if fonte not in FONTES_REAIS or len(barras) < MINIMO_BARRAS:
        return None

    try:
        preco = float(preco_atual)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(preco) or preco <= 0:
        return None

    ajustadas: List[BarraOHLC] = list(barras)
    ultima = ajustadas[-1]
    ajustadas[-1] = BarraOHLC(
        instante=ultima.instante,
        high=max(ultima.high, preco),
        low=min(ultima.low, preco),
        close=preco,
    )

    anterior_barra = ajustadas[-2].close
    if anterior_barra <= 0 or not math.isfinite(anterior_barra):
        return None

    anterior: Optional[float] = None
    variacao: Optional[float] = None
    if variacao_percentual is not None:
        try:
            variacao = float(variacao_percentual) / 100.0
        except (TypeError, ValueError):
            variacao = None
        if variacao is not None and math.isfinite(variacao) and (1.0 + variacao) != 0:
            candidato = preco / (1.0 + variacao)
            if (
                math.isfinite(candidato)
                and candidato > 0
                and abs(candidato - anterior_barra) / anterior_barra <= 0.005
            ):
                anterior = candidato
            else:
                variacao = None
                anterior = None

    if anterior is None or variacao is None:
        anterior = anterior_barra
        variacao = (preco / anterior_barra) - 1.0

    if not math.isfinite(variacao):
        return None

    if instante_mercado.tzinfo is None:
        instante = instante_mercado.replace(tzinfo=timezone.utc)
    else:
        instante = instante_mercado.astimezone(timezone.utc)

    return SerieMercado(
        ticker=ticker,
        preco_atual=preco,
        preco_fechamento_anterior=float(anterior),
        variacao_dia_pct=float(variacao),
        instante_mercado=instante,
        barras=tuple(ajustadas),
        fonte=fonte,
    )


def _epoch_para_datetime(valor) -> Optional[datetime]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return datetime.fromtimestamp(int(valor), timezone.utc)
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.isdigit():
            return datetime.fromtimestamp(int(texto), timezone.utc)
        try:
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _barra_valida(high, low, close, instante: Optional[datetime]) -> Optional[BarraOHLC]:
    if instante is None:
        return None
    try:
        h = float(high)
        l = float(low)
        c = float(close)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (h, l, c)):
        return None
    if l > h:
        l, h = h, l
    return BarraOHLC(instante=instante, high=h, low=l, close=c)


def interpretar_yahoo_chart(ticker: str, payload: dict) -> Optional[SerieMercado]:
    resultado = ((payload or {}).get("chart") or {}).get("result") or []
    if not resultado:
        return None
    bloco = resultado[0] or {}
    meta = bloco.get("meta") or {}
    timestamps = bloco.get("timestamp") or []
    quotes = ((bloco.get("indicators") or {}).get("quote") or [{}])
    quote = quotes[0] if quotes else {}
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []

    barras: List[BarraOHLC] = []
    n = min(len(timestamps), len(highs), len(lows), len(closes))
    for i in range(n):
        barra = _barra_valida(highs[i], lows[i], closes[i], _epoch_para_datetime(timestamps[i]))
        if barra is not None:
            barras.append(barra)
    if len(barras) < MINIMO_BARRAS:
        return None

    preco_meta = meta.get("regularMarketPrice")
    preco = float(preco_meta) if preco_meta is not None else barras[-1].close
    instante = _epoch_para_datetime(meta.get("regularMarketTime")) or barras[-1].instante
    return montar_serie(
        ticker,
        barras,
        preco,
        instante,
        meta.get("regularMarketChangePercent"),
        "yahoo",
    )


def buscar_yahoo(ticker: str) -> SerieMercado:
    simbolo = quote(ticker, safe="")
    params = {"interval": "1d", "range": "6mo"}
    ultimo_erro: Optional[Exception] = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{simbolo}"
        try:
            resposta = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
            resposta.raise_for_status()
            serie = interpretar_yahoo_chart(ticker, resposta.json())
            if serie is None:
                ultimo_erro = RuntimeError("histórico diário insuficiente")
                continue
            return serie
        except Exception as exc:  # noqa: BLE001 - a próxima fonte precisa do motivo
            ultimo_erro = exc
    raise RuntimeError(f"Yahoo Finance sem cotação utilizável ({ultimo_erro})")


def buscar_yfinance(ticker: str) -> SerieMercado:
    import pandas as pd
    import yfinance as yf

    quadro = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if quadro is None or getattr(quadro, "empty", True):
        raise RuntimeError("yfinance devolveu histórico vazio")

    if isinstance(quadro.columns, pd.MultiIndex):
        quadro = quadro.copy()
        quadro.columns = quadro.columns.get_level_values(0)

    colunas = {str(c).lower(): c for c in quadro.columns}
    if not {"high", "low", "close"}.issubset(colunas):
        raise RuntimeError("yfinance sem colunas High/Low/Close")

    barras: List[BarraOHLC] = []
    for indice, linha in quadro.iterrows():
        instante = _epoch_para_datetime(indice.to_pydatetime() if hasattr(indice, "to_pydatetime") else indice)
        barra = _barra_valida(linha[colunas["high"]], linha[colunas["low"]], linha[colunas["close"]], instante)
        if barra is not None:
            barras.append(barra)
    if len(barras) < MINIMO_BARRAS:
        raise RuntimeError("yfinance com menos de 20 pregões válidos")

    ultima = barras[-1]
    return montar_serie(ticker, barras, ultima.close, ultima.instante, None, "yfinance")


def interpretar_brapi(ticker: str, payload: dict) -> Optional[SerieMercado]:
    resultados = (payload or {}).get("results") or []
    if not resultados:
        return None
    item = resultados[0] or {}
    historico = item.get("historicalDataPrice") or []
    barras: List[BarraOHLC] = []
    for row in historico:
        if not isinstance(row, dict):
            continue
        fechamento = row.get("close")
        if fechamento is None:
            fechamento = row.get("adjustedClose")
        barra = _barra_valida(
            row.get("high"),
            row.get("low"),
            fechamento,
            _epoch_para_datetime(row.get("date")),
        )
        if barra is not None:
            barras.append(barra)
    barras.sort(key=lambda b: b.instante)
    if len(barras) < MINIMO_BARRAS:
        return None

    preco_meta = item.get("regularMarketPrice")
    preco = float(preco_meta) if preco_meta is not None else barras[-1].close
    instante = _epoch_para_datetime(item.get("regularMarketTime")) or barras[-1].instante
    return montar_serie(
        ticker,
        barras,
        preco,
        instante,
        item.get("regularMarketChangePercent"),
        "brapi",
    )


def buscar_brapi(ticker: str) -> SerieMercado:
    simbolo = BRAPI_SIMBOLOS.get(ticker)
    token = (os.getenv("BRAPI_TOKEN") or "").strip()
    if not simbolo or not token:
        raise RuntimeError("brapi não configurado para este ticker")
    resposta = requests.get(
        f"https://brapi.dev/api/quote/{quote(simbolo, safe='')}",
        params={"range": "6mo", "interval": "1d", "token": token},
        headers=HEADERS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    resposta.raise_for_status()
    serie = interpretar_brapi(ticker, resposta.json())
    if serie is None:
        raise RuntimeError("brapi sem histórico diário suficiente")
    return serie


def interpretar_cboe_vix(csv_texto: str) -> Optional[SerieMercado]:
    """
    Histórico oficial diário do VIX. O CSV traz a data do pregão, sem horário
    intradiário; o carimbo fica em 00:00 UTC dessa data.
    """
    barras: List[BarraOHLC] = []
    for linha in (csv_texto or "").splitlines():
        texto = linha.strip()
        if not texto or texto.lower().startswith("date"):
            continue
        partes = texto.split(",")
        if len(partes) < 5:
            continue
        try:
            dia = datetime.strptime(partes[0], "%m/%d/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        barra = _barra_valida(partes[2], partes[3], partes[4], dia)
        if barra is not None:
            barras.append(barra)
    if len(barras) < MINIMO_BARRAS:
        return None
    recentes = barras[-80:]
    ultima = recentes[-1]
    return montar_serie("^VIX", recentes, ultima.close, ultima.instante, None, "cboe")


def buscar_cboe_vix(ticker: str = "^VIX") -> SerieMercado:
    if ticker != "^VIX":
        raise RuntimeError("histórico CBOE desta integração cobre apenas o VIX")
    resposta = requests.get(
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        headers=HEADERS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    resposta.raise_for_status()
    serie = interpretar_cboe_vix(resposta.text)
    if serie is None:
        raise RuntimeError("CSV da CBOE sem 20 pregões válidos")
    return serie


def interpretar_awesome_usdbrl(payload) -> Optional[SerieMercado]:
    linhas = payload if isinstance(payload, list) else []
    pontos = []
    for row in linhas:
        if not isinstance(row, dict):
            continue
        instante = _epoch_para_datetime(row.get("timestamp"))
        barra = _barra_valida(row.get("high"), row.get("low"), row.get("bid") or row.get("ask"), instante)
        if barra is None:
            continue
        pontos.append((barra, row.get("pctChange")))
    if len(pontos) < MINIMO_BARRAS:
        return None

    pontos.sort(key=lambda item: item[0].instante)
    por_dia = {}
    for barra, pct in pontos:
        chave = barra.instante.date()
        atual = por_dia.get(chave)
        if atual is None:
            por_dia[chave] = [barra, pct]
            continue
        anterior = atual[0]
        por_dia[chave] = [
            BarraOHLC(
                instante=max(anterior.instante, barra.instante),
                high=max(anterior.high, barra.high),
                low=min(anterior.low, barra.low),
                close=barra.close,
            ),
            pct if pct not in (None, "") else atual[1],
        ]

    dias = [por_dia[chave] for chave in sorted(por_dia)]
    if len(dias) < MINIMO_BARRAS:
        return None
    barras = [dia[0] for dia in dias]
    pct = dias[-1][1]
    try:
        change = float(pct) if pct not in (None, "") else None
    except (TypeError, ValueError):
        change = None
    ultima = barras[-1]
    return montar_serie("USDBRL=X", barras, ultima.close, ultima.instante, change, "awesomeapi")


def buscar_awesome_usdbrl(ticker: str = "USDBRL=X") -> SerieMercado:
    if ticker != "USDBRL=X":
        raise RuntimeError("AwesomeAPI desta integração cobre apenas USD/BRL")
    resposta = requests.get(
        "https://economia.awesomeapi.com.br/json/daily/USD-BRL/90",
        headers=HEADERS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    resposta.raise_for_status()
    serie = interpretar_awesome_usdbrl(resposta.json())
    if serie is None:
        raise RuntimeError("AwesomeAPI sem 20 pregões de USD/BRL")
    return serie


def provedores_para(ticker: str):
    """Ordem de tentativa: Yahoo (chart e yfinance) e reservas específicas."""
    yield "yahoo", buscar_yahoo
    yield "yfinance", buscar_yfinance
    if ticker in BRAPI_SIMBOLOS and (os.getenv("BRAPI_TOKEN") or "").strip():
        yield "brapi", buscar_brapi
    if ticker == "^VIX":
        yield "cboe", buscar_cboe_vix
    if ticker == "USDBRL=X":
        yield "awesomeapi", buscar_awesome_usdbrl
