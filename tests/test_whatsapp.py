"""
Testes unitários para o notificador de WhatsApp e despachante de relatórios.
"""

from unittest.mock import MagicMock, patch
from src.agents.whatsapp_notifier import WhatsAppNotifier


def test_whatsapp_status_inicial_desconectado():
    wa = WhatsAppNotifier(telefone=None, apikey_callmebot=None)
    status = wa.obter_status()
    assert status.ativo is False
    assert status.modo == "nenhum"


def test_whatsapp_reconfigurar():
    wa = WhatsAppNotifier()
    wa.reconfigurar(telefone="+55 11 99999-8888", apikey_callmebot="key123")
    status = wa.obter_status()
    assert status.ativo is True
    assert status.modo == "callmebot"
    assert status.telefone == "5511999998888"


@patch("requests.get")
def test_whatsapp_enviar_mensagem(mock_get):
    mock_res = MagicMock()
    mock_res.ok = True
    mock_res.text = "Message sent successfully"
    mock_get.return_value = mock_res

    wa = WhatsAppNotifier(telefone="5511999998888", apikey_callmebot="key123")
    sucesso = wa.enviar_mensagem("Teste de mensagem quantitativa")
    assert sucesso is True
    assert mock_get.called


@patch("requests.get")
def test_whatsapp_enviar_relatorio(mock_get):
    mock_res = MagicMock()
    mock_res.ok = True
    mock_res.text = "Message sent"
    mock_get.return_value = mock_res

    wa = WhatsAppNotifier(telefone="5511999998888", apikey_callmebot="key123")
    cotacoes = {
        "BOVA11.SA": {"preco_atual": 165.40, "variacao_dia_pct": -0.0067, "zscore_20p": -1.89, "nome": "Ibovespa"}
    }
    sucesso = wa.enviar_relatorio_mercado(
        patrimonio_total=100.0,
        saldo_caixa=100.0,
        pnl_hoje=0.0,
        regime_macro="Reflação / Cautela",
        cotacoes=cotacoes,
        provedor_ia="Grok (xAI)",
    )
    assert sucesso is True
