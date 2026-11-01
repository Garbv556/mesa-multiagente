"""
Testes unitários para o conector BTG Pactual (Cloud & Sandbox).
"""

from unittest.mock import MagicMock, patch
import pytest
from src.execution.btg_connector import BTGConnector


def test_btg_status_inicial_sem_chaves():
    btg = BTGConnector()
    # Limpa variáveis de ambiente se existirem
    btg.client_id = None
    btg.client_secret = None
    btg.account_id = None
    status = btg.obter_status()
    assert status.conectado is False
    assert status.modo == "SANDBOX_SIMULADO"
    assert status.saldo_disponivel_brl == 100.0


def test_btg_reconfiguracao():
    btg = BTGConnector()
    btg.reconfigurar("meu_id", "meu_secret", "12345-6", "sandbox")
    assert btg.client_id == "meu_id"
    assert btg.client_secret == "meu_secret"
    assert btg.account_id == "12345-6"
    assert btg.ambiente == "sandbox"
    status = btg.obter_status()
    assert status.conectado is True
    assert status.modo == "SANDBOX_BTG"


def test_btg_envio_ordem_sandbox():
    btg = BTGConnector()
    resp = btg.enviar_ordem_b3(
        ativo="BOVA11.SA",
        tipo="COMPRA",
        quantidade=1.0,
        preco=165.40,
        stop_loss=154.06,
        take_profit=188.07,
    )
    assert resp.sucesso is True
    assert "BTG-SIM-BOVA11.SA" in resp.ordem_id_btg
    assert resp.status == "EXECUTADA_SIMULADA"
    assert resp.preco_executado == 165.40


@patch("requests.post")
def test_btg_envio_ordem_producao_sucesso(mock_post):
    # Simula autenticação e envio de ordem na B3
    mock_auth_res = MagicMock()
    mock_auth_res.ok = True
    mock_auth_res.json.return_value = {"access_token": "fake_token_jwt"}

    mock_order_res = MagicMock()
    mock_order_res.ok = True
    mock_order_res.json.return_value = {"orderId": "BTG-PROD-998877"}

    mock_post.side_effect = [mock_auth_res, mock_order_res]

    btg = BTGConnector(
        client_id="prod_id",
        client_secret="prod_secret",
        account_id="9999-1",
        ambiente="production",
    )
    resp = btg.enviar_ordem_b3(
        ativo="BOVA11.SA",
        tipo="COMPRA",
        quantidade=1.0,
        preco=165.40,
        stop_loss=154.06,
        take_profit=188.07,
    )

    assert resp.sucesso is True
    assert resp.ordem_id_btg == "BTG-PROD-998877"
    assert resp.status == "EXECUTADA"
