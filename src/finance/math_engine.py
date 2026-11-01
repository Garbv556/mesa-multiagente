"""
Motor Matemático e Quantitativo Determinístico.
Implementação estrita das formulações descritas no Documento Mestre
e no Manual de Arquitetura Multiagente.

Nenhuma lógica deste módulo depende de modelos probabilísticos de linguagem (LLMs).
Todos os cálculos são reproduzíveis e verificáveis.
"""

from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple
import numpy as np


def taxa_equivalente_composta(vp: float, vf: float, periodos: int) -> float:
    """
    Calcula a taxa periódica composta necessária para transformar VP em VF.
    i = (VF / VP)^(1/n) - 1
    """
    if vp <= 0 or vf <= 0 or periodos <= 0:
        raise ValueError("VP, VF e períodos devem ser maiores que zero.")
    return (vf / vp) ** (1.0 / periodos) - 1.0


def recuperacao_drawdown(d: float) -> float:
    """
    Calcula o ganho percentual necessário para recuperar uma perda D (Drawdown).
    G_rec = D / (1 - D)
    Exemplo: queda de 20% (d=0.20) exige ganho de 25% (0.25) para empatar.
    """
    if d < 0 or d >= 1.0:
        raise ValueError("Drawdown deve estar no intervalo [0, 1.0).")
    return d / (1.0 - d)


def expectativa_matematica_liquida(
    prob_vitoria: float,
    ganho_medio: float,
    perda_media: float,
    custo_total: float = 0.0,
) -> float:
    """
    Calcula a expectativa matemática líquida por operação.
    E = (Pw * Gm) - ((1 - Pw) * Lm) - Ctotal
    """
    if not (0.0 <= prob_vitoria <= 1.0):
        raise ValueError("Probabilidade de vitória deve estar entre 0 e 1.")
    prob_derrota = 1.0 - prob_vitoria
    return (prob_vitoria * ganho_medio) - (prob_derrota * perda_media) - custo_total


def kelly_fracionario(
    prob_sucesso: float,
    razao_ganho_perda: float,
    fracao: float = 0.25,
) -> float:
    """
    Calcula a fração ótima de capital a ser arriscada conforme Kelly Fracionado.
    f* = (b*p - q) / b = p - (q / b)
    f_operacional = fracao * f* (padrão: 0.25 = Quarter-Kelly)
    """
    if not (0.0 <= prob_sucesso <= 1.0):
        raise ValueError("Probabilidade de sucesso deve estar entre 0 e 1.")
    if razao_ganho_perda <= 0:
        raise ValueError("Razão de pagamento b (Gm/Lm) deve ser maior que zero.")

    q = 1.0 - prob_sucesso
    f_star = (razao_ganho_perda * prob_sucesso - q) / razao_ganho_perda

    if f_star <= 0:
        return 0.0

    return fracao * f_star


@dataclass(frozen=True)
class DimensionamentoOrdem:
    tamanho_lote: float
    risco_financeiro_brl: float
    fracao_patrimonio_arriscada: float
    fator_limitante: str


def dimensionar_posicao(
    patrimonio_liquido: float,
    preco_entrada: float,
    preco_stop_loss: float,
    prob_sucesso: float,
    razao_ganho_perda: float,
    risco_max_patrimonio_pct: float = 0.02,
    fracao_kelly: float = 0.25,
) -> DimensionamentoOrdem:
    """
    Dimensiona o tamanho da posição com Quarter-Kelly e trava rígida máxima de 2% de risco.
    """
    if patrimonio_liquido <= 0:
        return DimensionamentoOrdem(0.0, 0.0, 0.0, "Patrimonio insuficiente")

    distancia_stop = abs(preco_entrada - preco_stop_loss)
    if distancia_stop <= 0:
        raise ValueError("Distância até o Stop Loss não pode ser zero.")

    f_kelly = kelly_fracionario(prob_sucesso, razao_ganho_perda, fracao=fracao_kelly)

    if f_kelly <= 0:
        return DimensionamentoOrdem(0.0, 0.0, 0.0, "Expectativa negativa (Kelly <= 0)")

    # Limite 1: Trava máxima rígida de risco por operação (ex: 2% do patrimônio)
    risco_max_financeiro = patrimonio_liquido * risco_max_patrimonio_pct
    lote_pela_trava_risco = risco_max_financeiro / distancia_stop

    # Limite 2: Alocação sugerida pelo Kelly Fracionado
    capital_kelly = patrimonio_liquido * f_kelly
    lote_pelo_kelly = capital_kelly / preco_entrada

    # O lote real não pode violar nem o capital disponível nem o risco máximo tolerado
    if lote_pela_trava_risco <= lote_pelo_kelly:
        lote_final = lote_pela_trava_risco
        fator = "Trava rígida de 2% de risco"
    else:
        lote_final = lote_pelo_kelly
        fator = "Critério Quarter-Kelly"

    risco_financeiro_real = lote_final * distancia_stop
    fracao_risco_real = risco_financeiro_real / patrimonio_liquido

    return DimensionamentoOrdem(
        tamanho_lote=lote_final,
        risco_financeiro_brl=risco_financeiro_real,
        fracao_patrimonio_arriscada=fracao_risco_real,
        fator_limitante=fator,
    )


def calcular_zscore(serie: Sequence[float], valor_atual: float) -> float:
    """
    Calcula a normalização Z-Score do valor atual em relação à janela histórica.
    Z = (X_atual - mu) / sigma
    """
    arr = np.asarray(serie, dtype=float)
    if len(arr) < 2:
        raise ValueError("A série deve conter no mínimo 2 observações.")
    mu = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1))
    if sigma == 0:
        return 0.0
    return (valor_atual - mu) / sigma


def calcular_atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], periodo: int = 14
) -> float:
    """
    Calcula o Average True Range (ATR) para a janela informada.
    TR = max(H - L, |H - C_prev|, |L - C_prev|)
    """
    if len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("As séries de high, low e close devem ter o mesmo tamanho.")
    if len(highs) < periodo + 1:
        raise ValueError(f"Série insuficiente para período {periodo}.")

    tr_list = []
    for i in range(1, len(highs)):
        h = highs[i]
        l = lows[i]
        c_prev = closes[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)

    return float(np.mean(tr_list[-periodo:]))


def calcular_drawdown_maximo(curva_patrimonio: Sequence[float]) -> Tuple[float, float]:
    """
    Calcula o drawdown atual e o drawdown máximo histórico a partir da série de patrimônio.
    Retorna (drawdown_atual, max_drawdown) expressos como números positivos (ex: 0.25 = 25% de queda).
    """
    valores = np.asarray(curva_patrimonio, dtype=float)
    if len(valores) == 0:
        return 0.0, 0.0

    picos = np.maximum.accumulate(valores)
    drawdowns = (picos - valores) / picos
    max_dd = float(np.max(drawdowns))
    dd_atual = float(drawdowns[-1])
    return dd_atual, max_dd


def calcular_sharpe_sortino(
    retornos: Sequence[float],
    taxa_livre_risco_periodo: float = 0.0,
) -> Tuple[float, float]:
    """
    Calcula Índice de Sharpe e Índice de Sortino.
    Sortino considera apenas o desvio-padrão dos retornos negativos (downside risk).
    """
    arr = np.asarray(retornos, dtype=float)
    if len(arr) < 2:
        return 0.0, 0.0

    retorno_excedente = arr - taxa_livre_risco_periodo
    media_excedente = float(np.mean(retorno_excedente))
    desvio_total = float(np.std(arr, ddof=1))

    sharpe = (media_excedente / desvio_total) if desvio_total > 0 else 0.0

    retornos_negativos = retorno_excedente[retorno_excedente < 0]
    if len(retornos_negativos) > 1:
        desvio_downside = float(np.std(retornos_negativos, ddof=1))
        sortino = (media_excedente / desvio_downside) if desvio_downside > 0 else 0.0
    else:
        sortino = sharpe

    return sharpe, sortino


def var_parametrico(
    patrimonio: float,
    volatilidade_diaria: float,
    nivel_confianca: float = 0.95,
    horizonte_dias: int = 1,
) -> float:
    """
    Value at Risk (VaR) paramétrico.
    VaR = Patrimonio * Z_alpha * sigma_diario * sqrt(t)
    Exemplo: 95% -> Z = 1.645 | 99% -> Z = 2.326
    """
    z_map = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z_alpha = z_map.get(nivel_confianca, 1.645)
    return patrimonio * z_alpha * volatilidade_diaria * math.sqrt(horizonte_dias)
