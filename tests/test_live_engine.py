"""
Testes unitários para a LiveMarketEngine (Ticks em tempo real e micro-oscilações).
"""

from src.collectors.live_engine import LiveMarketEngine


def test_live_market_engine_carregamento():
    engine = LiveMarketEngine()
    cotacoes = engine.obter_cotacoes()
    assert "BOVA11.SA" in cotacoes
    assert "IVVB11.SA" in cotacoes
    assert "GOLD11.SA" in cotacoes
    assert "USDBRL=X" in cotacoes
    assert "^VIX" in cotacoes


def test_live_market_engine_ticks_dinamicos():
    engine = LiveMarketEngine()
    tick1 = engine.gerar_tick_ao_vivo()
    preco_inicial = {k: v["preco_atual"] for k, v in tick1.items()}

    # Executa múltiplos ticks
    for _ in range(5):
        tick_novo = engine.gerar_tick_ao_vivo()

    precos_novos = {k: v["preco_atual"] for k, v in tick_novo.items()}
    # Pelo menos um ativo deve ter oscilado realisticamente
    assert any(precos_novos[k] != preco_inicial[k] for k in precos_novos)
