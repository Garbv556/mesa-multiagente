"""
Testes unitários do Notificador Telegram.
"""

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.agents.telegram_notifier import TelegramNotifier

client = TestClient(app)


def test_telegram_status_desconectado(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = TelegramNotifier()
    status = tg.obter_status()
    assert status.ativo is False


def test_telegram_notificar_proposta_mock():
    tg = TelegramNotifier(bot_token="fake_token", chat_id="123456789")
    with patch("requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {"ok": True}

        prop = {
            "ativo": "BOVA11.SA",
            "tipo": "COMPRA",
            "preco_atual": 165.4,
            "preco_stop_loss": 154.06,
            "preco_take_profit": 188.07,
            "probabilidade": 0.78,
            "justificativa": "Teste quantitativo",
            "revisor_parecer": "APROVADO",
        }
        resultado = tg.notificar_proposta_trade(prop)
        assert resultado is True
        assert mock_post.called


def test_api_telegram_status():
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    assert "ativo" in resp.json()
