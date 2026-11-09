"""
Testes dos endpoints da API do Dashboard.
"""

from fastapi.testclient import TestClient
from src.dashboard.app import app

client = TestClient(app)


def test_get_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "Mesa Multiagente" in response.text


def test_get_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "patrimonio_total" in data
    assert data["capital_inicial"] == 100.0


def test_get_proposals_e_orders():
    resp_prop = client.get("/api/proposals")
    assert resp_prop.status_code == 200

    resp_orders = client.get("/api/orders")
    assert resp_orders.status_code == 200


def test_get_feed():
    resp_feed = client.get("/api/feed")
    assert resp_feed.status_code == 200
    eventos = resp_feed.json()
    assert isinstance(eventos, list)
    assert len(eventos) > 0
    assert "tag" in eventos[0]


def test_market_sem_fonte_nao_inventa_preco(monkeypatch, tmp_path):
    from src.collectors.live_engine import LiveMarketEngine
    from src.dashboard import app as painel

    class FonteMorta:
        tickers = ["BOVA11.SA", "IVVB11.SA", "GOLD11.SA", "USDBRL=X", "^VIX"]
        erros = {"BOVA11.SA": "yahoo: timeout"}

        def coletar_cesta_completa(self):
            return {}

    engine = LiveMarketEngine(
        coletor=FonteMorta(),
        caminho_snapshot=str(tmp_path / "vazio.json"),
        ttl_segundos=0,
    )
    monkeypatch.setattr(painel, "live_market", engine)

    response = client.get("/api/market")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == set(FonteMorta.tickers)
    assert data["BOVA11.SA"]["disponivel"] is False
    assert data["BOVA11.SA"]["preco_atual"] is None
    assert "165.4" not in response.text


def test_get_whatsapp_status():
    resp = client.get("/api/whatsapp/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "ativo" in data
    assert "modo" in data


