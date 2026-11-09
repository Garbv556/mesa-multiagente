"""A mesa repete a última coleta real e não passeia o preço."""

from datetime import datetime, timezone
import json
from pathlib import Path

from src.collectors.live_engine import LiveMarketEngine
from src.collectors.market_data import MetricasAtivo, TICKERS_CESTA


def _metrica(ticker: str, preco: float) -> MetricasAtivo:
    agora = datetime.now(timezone.utc).isoformat()
    return MetricasAtivo(
        ticker=ticker,
        preco_atual=preco,
        preco_fechamento_anterior=preco - 1,
        variacao_dia_pct=1 / preco,
        zscore_20p=-0.4,
        atr_14p=1.25,
        volatilidade_20p=0.012,
        tempo_referencia=agora,
        tempo_evento=agora,
        tempo_publicacao=agora,
        tempo_coleta=agora,
        nome="Teste",
        categoria="B3",
        variacao_nominal=1.0,
        sparkline=[preco - 1, preco],
        fonte="yahoo",
    )


class _ColetorScript:
    def __init__(self, falhar_apos: int | None = None):
        self.chamadas = 0
        self.falhar_apos = falhar_apos
        self.tickers = list(TICKERS_CESTA)
        self.erros = {}

    def coletar_cesta_completa(self):
        self.chamadas += 1
        if self.falhar_apos is not None and self.chamadas > self.falhar_apos:
            self.erros = {ticker: "fonte sem resposta" for ticker in self.tickers}
            return {}
        return {ticker: _metrica(ticker, 100.0 + indice) for indice, ticker in enumerate(self.tickers)}


def _engine(tmp_path: Path, coletor, ttl: int = 0, validade: int = 100000) -> LiveMarketEngine:
    return LiveMarketEngine(
        coletor=coletor,
        caminho_snapshot=str(tmp_path / "mercado.json"),
        ttl_segundos=ttl,
        validade_stale_segundos=validade,
    )


def test_cotacao_nao_oscila_entre_leituras(tmp_path):
    coletor = _ColetorScript()
    engine = _engine(tmp_path, coletor, ttl=3600)
    primeira = engine.obter_cotacoes()
    segunda = engine.obter_cotacoes()

    assert coletor.chamadas == 1
    assert set(primeira) == set(TICKERS_CESTA)
    for ticker in TICKERS_CESTA:
        assert primeira[ticker]["preco_atual"] == segunda[ticker]["preco_atual"]
        assert primeira[ticker]["sparkline"] == segunda[ticker]["sparkline"]
        assert primeira[ticker]["disponivel"] is True
        assert primeira[ticker]["fonte"] == "yahoo"
        assert primeira[ticker]["dados_stale"] is False


def test_falha_de_fonte_marca_stale_sem_mexer_no_preco(tmp_path):
    coletor = _ColetorScript(falhar_apos=1)
    engine = _engine(tmp_path, coletor, ttl=0)
    primeira = engine.obter_cotacoes()
    segunda = engine.obter_cotacoes()

    assert coletor.chamadas == 2
    for ticker in TICKERS_CESTA:
        assert segunda[ticker]["preco_atual"] == primeira[ticker]["preco_atual"]
        assert segunda[ticker]["dados_stale"] is True
        assert segunda[ticker]["disponivel"] is True
        assert "desatualizada" in segunda[ticker]["aviso"]


def test_snapshot_sem_fonte_real_nao_entra_na_api(tmp_path):
    caminho = tmp_path / "mercado.json"
    caminho.write_text(
        json.dumps(
            {
                "BOVA11.SA": {
                    "ticker": "BOVA11.SA",
                    "preco_atual": 165.40,
                    "tempo_referencia": "2026-10-30",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "sparkline": [205.5, 201.7, 172.4, 165.4],
                }
            }
        ),
        encoding="utf-8",
    )
    engine = _engine(tmp_path, _ColetorScript(falhar_apos=0), ttl=0)
    cotacoes = engine.obter_cotacoes()
    texto = json.dumps(cotacoes)

    assert cotacoes["BOVA11.SA"]["disponivel"] is False
    assert cotacoes["BOVA11.SA"]["preco_atual"] is None
    assert "165.4" not in texto
    assert "172.4" not in texto
    assert "2026-10-30" not in texto


def test_cache_real_antigo_so_aparece_como_stale(tmp_path):
    agora = datetime.now(timezone.utc).isoformat()
    caminho = tmp_path / "mercado.json"
    caminho.write_text(
        json.dumps(
            {
                "BOVA11.SA": {
                    "ticker": "BOVA11.SA",
                    "preco_atual": 166.94,
                    "preco_fechamento_anterior": 165.93,
                    "variacao_dia_pct": 0.006,
                    "zscore_20p": 0.2,
                    "atr_14p": 1.1,
                    "volatilidade_20p": 0.01,
                    "tempo_referencia": agora,
                    "tempo_evento": agora,
                    "tempo_publicacao": agora,
                    "tempo_coleta": agora,
                    "nome": "iShares Ibovespa",
                    "categoria": "B3",
                    "variacao_nominal": 1.01,
                    "sparkline": [166.0, 166.94],
                    "fonte": "yahoo",
                    "disponivel": True,
                }
            }
        ),
        encoding="utf-8",
    )
    engine = _engine(tmp_path, _ColetorScript(falhar_apos=0), ttl=0)
    bova = engine.obter_cotacoes()["BOVA11.SA"]
    assert bova["preco_atual"] == 166.94
    assert bova["dados_stale"] is True
    assert bova["fonte"] == "yahoo"


def test_codigo_de_coleta_nao_sorteia_preco():
    raiz = Path("src/collectors")
    texto = "\n".join(caminho.read_text(encoding="utf-8") for caminho in raiz.glob("*.py"))
    assert "random." not in texto
    painel = Path("src/dashboard/app.py").read_text(encoding="utf-8")
    assert "random." not in painel
    assert "165.40" not in painel
    html = Path("src/dashboard/templates/index.html").read_text(encoding="utf-8")
    for trecho in ("-1.89", "+1.75", "19.42", "12,91", "154,06"):
        assert trecho not in html
