"""
Testes unitários do Order Gate e do Simulador de Carteira.
Garante a eficácia das travas de risco da Fase Semente (R$ 100,00).
"""

import pytest
from src.execution.portfolio_simulator import CarteiraSimulada, TipoOperacao, EstadoOrdem
from src.execution.order_gate import OrderGate, PropostaTrade


@pytest.fixture
def order_gate_instancia():
    carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
    gate = OrderGate(caminho_config="config/risk_limits.json", carteira=carteira)
    return gate, carteira


def test_order_gate_sucesso(order_gate_instancia):
    gate, carteira = order_gate_instancia
    proposta = PropostaTrade(
        proposta_id="PROP-001",
        ativo="BOVA11.SA",
        tipo=TipoOperacao.COMPRA,
        preco_atual=100.0,
        preco_bid=99.95,
        preco_ask=100.05,  # spread = 0.10 / 100 = 0.10% (< 0.15%)
        preco_stop_loss=98.0,  # perda = R$ 2.00
        preco_take_profit=104.0,  # ganho = R$ 4.00 (b = 2.0)
        probabilidade_sucesso=0.80,  # >= 0.75
        vies_macro="LONG",
        justificativa="Estiramento estatístico alinhado com viés macro favorável.",
    )

    decisao = gate.avaliar_e_executar(proposta)
    assert decisao.autorizado is True
    assert decisao.ordem_gerada is not None
    assert decisao.ordem_gerada.estado == EstadoOrdem.EXECUTADA
    # O risco não pode ultrapassar 2% de R$ 100 (R$ 2.00)
    assert decisao.dimensionamento.risco_financeiro_brl <= 2.0001


def test_order_gate_bloqueio_baixa_confianca(order_gate_instancia):
    gate, carteira = order_gate_instancia
    proposta = PropostaTrade(
        proposta_id="PROP-002",
        ativo="BOVA11.SA",
        tipo=TipoOperacao.COMPRA,
        preco_atual=100.0,
        preco_bid=99.95,
        preco_ask=100.05,
        preco_stop_loss=98.0,
        preco_take_profit=104.0,
        probabilidade_sucesso=0.70,  # < 0.75 exigido
        vies_macro="LONG",
        justificativa="Setup com sinal fraco.",
    )

    decisao = gate.avaliar_e_executar(proposta)
    assert decisao.autorizado is False
    assert "Probabilidade" in decisao.motivo


def test_order_gate_bloqueio_vies_macro(order_gate_instancia):
    gate, carteira = order_gate_instancia
    proposta = PropostaTrade(
        proposta_id="PROP-003",
        ativo="BOVA11.SA",
        tipo=TipoOperacao.COMPRA,
        preco_atual=100.0,
        preco_bid=99.95,
        preco_ask=100.05,
        preco_stop_loss=98.0,
        preco_take_profit=104.0,
        probabilidade_sucesso=0.85,
        vies_macro="SHORT",  # Viés macro oposto
        justificativa="Tentativa contra a tendência macro.",
    )

    decisao = gate.avaliar_e_executar(proposta)
    assert decisao.autorizado is False
    assert "viés macro" in decisao.motivo


def test_order_gate_bloqueio_spread_excessivo(order_gate_instancia):
    gate, carteira = order_gate_instancia
    proposta = PropostaTrade(
        proposta_id="PROP-004",
        ativo="GOLD11.SA",
        tipo=TipoOperacao.COMPRA,
        preco_atual=50.0,
        preco_bid=49.80,
        preco_ask=50.20,  # spread = 0.40 / 50 = 0.80% (> 0.15%)
        preco_stop_loss=48.0,
        preco_take_profit=54.0,
        probabilidade_sucesso=0.80,
        vies_macro="LONG",
        justificativa="Spread elevado.",
    )

    decisao = gate.avaliar_e_executar(proposta)
    assert decisao.autorizado is False
    assert "Spread" in decisao.motivo


def test_order_gate_bloqueio_duas_perdas_consecutivas(order_gate_instancia):
    gate, carteira = order_gate_instancia
    carteira.perdas_consecutivas_hoje = 2  # Simula duas perdas hoje

    proposta = PropostaTrade(
        proposta_id="PROP-005",
        ativo="BOVA11.SA",
        tipo=TipoOperacao.COMPRA,
        preco_atual=100.0,
        preco_bid=99.95,
        preco_ask=100.05,
        preco_stop_loss=98.0,
        preco_take_profit=104.0,
        probabilidade_sucesso=0.90,
        vies_macro="LONG",
        justificativa="Boa oportunidade após perdas.",
    )

    decisao = gate.avaliar_e_executar(proposta)
    assert decisao.autorizado is False
    assert "perdas consecutivas" in decisao.motivo
