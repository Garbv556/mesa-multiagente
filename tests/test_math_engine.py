"""
Testes unitários do motor matemático determinístico.
Verifica a fidelidade dos cálculos em relação aos exemplos e laboratórios
apresentados nos manuais do projeto.
"""

import pytest
from src.finance.math_engine import (
    taxa_equivalente_composta,
    recuperacao_drawdown,
    expectativa_matematica_liquida,
    kelly_fracionario,
    dimensionar_posicao,
    calcular_zscore,
    calcular_atr,
    calcular_drawdown_maximo,
    var_parametrico,
)


def test_recuperacao_drawdown():
    # Laboratório 2 do PDF: queda de 20% exige alta de 25% para recuperar
    g_rec = recuperacao_drawdown(0.20)
    assert pytest.approx(g_rec, 0.0001) == 0.25

    # Perda de 50% exige +100%
    assert pytest.approx(recuperacao_drawdown(0.50), 0.0001) == 1.00

    # Perda de 10% exige +11.11%
    assert pytest.approx(recuperacao_drawdown(0.10), 0.0001) == 0.111111


def test_taxa_composta_meta():
    # PDF Seção 3.1: R$ 100 -> R$ 250 (+150%)
    # Em 12 meses: 7.93% ao mês
    i_12 = taxa_equivalente_composta(100.0, 250.0, 12)
    assert pytest.approx(i_12, 0.001) == 0.0793

    # Em 24 meses: 3.89% ao mês
    i_24 = taxa_equivalente_composta(100.0, 250.0, 24)
    assert pytest.approx(i_24, 0.001) == 0.0389

    # Em 36 meses: 2.58% ao mês
    i_36 = taxa_equivalente_composta(100.0, 250.0, 36)
    assert pytest.approx(i_36, 0.001) == 0.0258


def test_expectativa_matematica_liquida():
    # PDF Seção 3.2: Pw = 0.45, Gm = 3.00, Lm = 1.50
    # Bruto: +R$ 0.525
    e_bruta = expectativa_matematica_liquida(0.45, 3.00, 1.50, custo_total=0.0)
    assert pytest.approx(e_bruta, 0.0001) == 0.525

    # Com custo de R$ 0.60 por operação, torna-se negativa (-R$ 0.075)
    e_liquida = expectativa_matematica_liquida(0.45, 3.00, 1.50, custo_total=0.60)
    assert pytest.approx(e_liquida, 0.0001) == -0.075


def test_kelly_fracionario():
    # PDF Seção 3.3: p = 0.45, b = 2.0 (3.00 / 1.50)
    # f* = (2 * 0.45 - 0.55) / 2 = 0.35 / 2 = 0.175
    # f_operacional = 0.25 * 0.175 = 0.04375
    f_operacional = kelly_fracionario(0.45, 2.0, fracao=0.25)
    assert pytest.approx(f_operacional, 0.0001) == 0.04375


def test_dimensionamento_com_trava_de_dois_por_cento():
    # Banca de R$ 100,00 -> risco máximo de 2% = R$ 2,00
    patrimonio = 100.0
    preco_entrada = 10.0
    preco_stop = 9.0  # distância = R$ 1,00
    prob_sucesso = 0.60
    razao_b = 2.0

    ordem = dimensionar_posicao(
        patrimonio_liquido=patrimonio,
        preco_entrada=preco_entrada,
        preco_stop_loss=preco_stop,
        prob_sucesso=prob_sucesso,
        razao_ganho_perda=razao_b,
        risco_max_patrimonio_pct=0.02,
        fracao_kelly=0.25,
    )

    # Risco financeiro não pode ultrapassar R$ 2,00
    assert ordem.risco_financeiro_brl <= 2.0001
    assert ordem.fracao_patrimonio_arriscada <= 0.02001


def test_calcular_drawdown_maximo():
    # Laboratório do PDF: carteira vai de 100 a 120, cai a 90 e volta a 110
    # Queda máxima do pico (120 até 90) é 30/120 = 25% (0.25)
    historico = [100.0, 120.0, 90.0, 110.0]
    dd_atual, max_dd = calcular_drawdown_maximo(historico)
    assert pytest.approx(max_dd, 0.0001) == 0.25
    # Do pico de 120 para 110: (120 - 110) / 120 = 10 / 120 = 8.33%
    assert pytest.approx(dd_atual, 0.0001) == 10.0 / 120.0


def test_calcular_zscore():
    serie = [10.0, 10.0, 10.0, 10.0, 10.0]
    # Com variância zero, zscore deve ser 0
    assert calcular_zscore(serie, 10.0) == 0.0

    serie_var = [10.0, 20.0, 30.0, 40.0, 50.0]
    z = calcular_zscore(serie_var, 30.0)
    assert pytest.approx(z, 0.0001) == 0.0  # Média é 30


def test_var_parametrico():
    # R$ 100,00 de patrimônio, volatilidade diária de 2% (0.02), 95% de confiança (Z=1.645)
    var_1d = var_parametrico(100.0, 0.02, nivel_confianca=0.95, horizonte_dias=1)
    assert pytest.approx(var_1d, 0.001) == 100.0 * 1.645 * 0.02
