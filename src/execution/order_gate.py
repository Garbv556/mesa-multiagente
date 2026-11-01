"""
Order Gate - O Portão de Execução e Travas Rígidas.
Garante que NENHUMA ordem sugerida por agente de IA seja executada
se violar qualquer regra matemática, limite de risco ou diretriz de governança.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional, Tuple
from src.execution.portfolio_simulator import CarteiraSimulada, Ordem, EstadoOrdem, TipoOperacao
from src.finance.math_engine import dimensionar_posicao, DimensionamentoOrdem


@dataclass
class PropostaTrade:
    proposta_id: str
    ativo: str
    tipo: TipoOperacao
    preco_atual: float
    preco_bid: float
    preco_ask: float
    preco_stop_loss: float
    preco_take_profit: float
    probabilidade_sucesso: float
    vies_macro: str  # "LONG", "SHORT", "NEUTRAL"
    justificativa: str


@dataclass
class DecisaoGate:
    autorizado: bool
    motivo: str
    dimensionamento: Optional[DimensionamentoOrdem] = None
    ordem_gerada: Optional[Ordem] = None


class OrderGate:
    def __init__(self, caminho_config: str, carteira: CarteiraSimulada):
        self.caminho_config = Path(caminho_config)
        self.carteira = carteira
        self.regras = self._carregar_regras()

    def _carregar_regras(self) -> dict:
        if not self.caminho_config.exists():
            raise FileNotFoundError(f"Arquivo de regras não encontrado: {self.caminho_config}")
        with open(self.caminho_config, "r", encoding="utf-8") as f:
            return json.load(f)

    def avaliar_e_executar(self, proposta: PropostaTrade) -> DecisaoGate:
        travas = self.regras.get("travas_risco_operacional", {})
        confianca_min = travas.get("confianca_minima_execucao", 0.75)
        spread_max = travas.get("spread_bid_ask_max_pct", 0.0015)
        perda_max_diaria_pct = travas.get("perda_max_diaria_pct", 0.04)
        max_perdas_seguidas = travas.get("trava_perdas_consecutivas", 2)
        risco_max_pct = travas.get("risco_max_por_trade_pct", 0.02)
        fracao_kelly = travas.get("criterio_kelly_fracionado", 0.25)

        # 1. Trava de perdas consecutivas
        if self.carteira.perdas_consecutivas_hoje >= max_perdas_seguidas:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: limite de {max_perdas_seguidas} perdas consecutivas atingido hoje.",
            )

        # 2. Trava de stop diário
        limite_perda_diaria = self.carteira.capital_inicial * perda_max_diaria_pct
        if self.carteira.pl_realizado_hoje <= -limite_perda_diaria:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: Stop diário de {perda_max_diaria_pct*100}% atingido (-R$ {limite_perda_diaria:.2f}).",
            )

        # 3. Trava de confiança mínima da IA
        if proposta.probabilidade_sucesso < confianca_min:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: Probabilidade de {proposta.probabilidade_sucesso:.2f} inferior ao mínimo de {confianca_min:.2f}.",
            )

        # 4. Trava de alinhamento macro
        if proposta.tipo == TipoOperacao.COMPRA and proposta.vies_macro != "LONG":
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: Compra em desacordo com viés macro vigente ({proposta.vies_macro}).",
            )

        # 5. Trava de Spread Bid-Ask (custo invisível)
        if proposta.preco_ask > 0 and proposta.preco_bid > 0:
            spread = (proposta.preco_ask - proposta.preco_bid) / proposta.preco_atual
            if spread > spread_max:
                return DecisaoGate(
                    autorizado=False,
                    motivo=f"Bloqueio: Spread ({spread:.4%}) supera o teto de {spread_max:.4%}.",
                )

        # 6. Cálculo da razão ganho / perda (b)
        distancia_ganho = abs(proposta.preco_take_profit - proposta.preco_atual)
        distancia_perda = abs(proposta.preco_atual - proposta.preco_stop_loss)
        if distancia_perda <= 0:
            return DecisaoGate(
                autorizado=False,
                motivo="Bloqueio: Distância para Stop Loss inválida (zero ou negativa).",
            )
        razao_b = distancia_ganho / distancia_perda
        if razao_b < 1.0:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: Relação Retorno/Risco ({razao_b:.2f}) desfavorável (exigido >= 1.0).",
            )

        # 7. Dimensionamento determinístico de posição (Quarter-Kelly + Trava de 2%)
        dim = dimensionar_posicao(
            patrimonio_liquido=self.carteira.patrimonio_total,
            preco_entrada=proposta.preco_atual,
            preco_stop_loss=proposta.preco_stop_loss,
            prob_sucesso=proposta.probabilidade_sucesso,
            razao_ganho_perda=razao_b,
            risco_max_patrimonio_pct=risco_max_pct,
            fracao_kelly=fracao_kelly,
        )

        if dim.tamanho_lote <= 0.00001:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Bloqueio: Lote calculado nulo ({dim.fator_limitante}).",
                dimensionamento=dim,
            )

        # 8. Execução no simulador
        if proposta.tipo == TipoOperacao.COMPRA:
            ordem = self.carteira.executar_compra(
                ativo=proposta.ativo,
                quantidade=dim.tamanho_lote,
                preco=proposta.preco_atual,
                preco_stop_loss=proposta.preco_stop_loss,
                preco_take_profit=proposta.preco_take_profit,
                taxa_corretagem=0.0,
                justificativa=f"Aprovado pelo OrderGate ({dim.fator_limitante}): {proposta.justificativa}",
            )
        else:
            ordem = self.carteira.executar_venda(
                ativo=proposta.ativo,
                quantidade=dim.tamanho_lote,
                preco=proposta.preco_atual,
                taxa_corretagem=0.0,
                justificativa=f"Aprovado pelo OrderGate ({dim.fator_limitante}): {proposta.justificativa}",
            )

        if ordem.estado != EstadoOrdem.EXECUTADA:
            return DecisaoGate(
                autorizado=False,
                motivo=f"Falha de execução na carteira: {ordem.justificativa}",
                dimensionamento=dim,
                ordem_gerada=ordem,
            )

        return DecisaoGate(
            autorizado=True,
            motivo=f"Ordem validada e executada com sucesso ({dim.fator_limitante}).",
            dimensionamento=dim,
            ordem_gerada=ordem,
        )
