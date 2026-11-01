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

