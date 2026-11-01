"""
Coordenador do Ciclo Operacional Mínimo.
Conecta os dados coletados ao Analista, submete ao Revisor e envia as propostas aprovadas
ao Order Gate para execução na Carteira Simulada.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Any, List

from src.collectors.market_data import ColetorMercado
from src.execution.portfolio_simulator import CarteiraSimulada, TipoOperacao
from src.execution.order_gate import OrderGate, PropostaTrade
from src.agents.contracts import (
    DiagnosticoMercado,
    PropostaAnalista,
    RelatorioRevisao,
    ParecerRevisao,
    ViesDirecional,
)


class CoordenadorCiclo:
    def __init__(self, caminho_config: str = "config/risk_limits.json"):
        self.caminho_config = caminho_config
        self.carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
        self.gate = OrderGate(caminho_config=self.caminho_config, carteira=self.carteira)
        self.coletor = ColetorMercado()

    def analisar_mercado_deterministico(self, snapshot: Dict[str, Any]) -> DiagnosticoMercado:
        """
        Gera análise preliminar com base nas regras do catálogo quantitativo (/notebook_kb/03_catalogo_setups_quant.json).
        Se Z-Score < -1.8 com viés favorável, gera proposta LONG com Stop Loss em 1.5 * ATR.
        """
        propostas: List[PropostaAnalista] = []
        agora = datetime.now(timezone.utc).isoformat()

        # Determinação do regime macro (exemplo simplificado: DXY/USDBRL alto -> cautela/reflação)
        usd = snapshot.get("USDBRL=X", {})
        z_usd = usd.get("zscore_20p", 0.0)
        regime = "Reflação / Cautela Cambial" if z_usd > 1.5 else "Goldilocks / Neutro"

        for ticker, metricas in snapshot.items():
            if ticker == "USDBRL=X":
                continue

            zscore = metricas.get("zscore_20p", 0.0)
            preco = metricas.get("preco_atual", 0.0)
            atr = metricas.get("atr_14p", 1.0)

            # Setup Retorno à Média (Mean Reversion): Z-Score esticado para baixo
            if zscore <= -1.8:
                distancia_stop = 1.5 * atr
                preco_stop = preco - distancia_stop
                preco_alvo = preco + (2.0 * distancia_stop)  # Razão 2:1

                propostas.append(
                    PropostaAnalista(
                        ativo=ticker,
                        tipo_operacao="COMPRA",
                        preco_referencia=preco,
                        preco_stop_loss=preco_stop,
                        preco_take_profit=preco_alvo,
                        probabilidade_estimada=0.78,
                        justificativa_quant=f"Z-Score estirado em {zscore:.2f} com ATR de R$ {atr:.2f}",
                        vies_macro=ViesDirecional.LONG,
                    )
                )

        return DiagnosticoMercado(
            regime_macro_vigente=regime,
            resumo_cenario=f"Monitoramento de {len(snapshot)} ativos. Dólar Z={z_usd:.2f}.",
            propostas=propostas,
            timestamp_geracao=agora,
        )

    def revisar_proposta(self, proposta: PropostaAnalista, metricas_ativo: dict) -> RelatorioRevisao:
        """
        O Revisor audita a consistência das contas e a atualidade dos dados.
        """
        contrapontos = []
        inconsistencias = []

        # Conferência de validade temporal
        tempo_coleta = metricas_ativo.get("tempo_coleta")
        if not tempo_coleta:
            inconsistencias.append("Dado sem timestamp de coleta.")

        # Auditoria matemática de Stop Loss e Take Profit
        distancia_perda = proposta.preco_referencia - proposta.preco_stop_loss
        distancia_ganho = proposta.preco_take_profit - proposta.preco_referencia

        if distancia_perda <= 0:
            inconsistencias.append("Preço de Stop Loss incoerente (acima ou igual ao preço de entrada).")
        if distancia_ganho < distancia_perda:
            contrapontos.append("Relação Retorno/Risco inferior a 1.0.")

        if proposta.probabilidade_estimada < 0.75:
            contrapontos.append("Probabilidade declarada abaixo da nota de corte da política de risco (0.75).")

        valido = len(inconsistencias) == 0 and len(contrapontos) == 0
        parecer = ParecerRevisao.APROVADO if valido else ParecerRevisao.REJEITADO

        return RelatorioRevisao(
            parecer=parecer,
            contrapontos_identificados=contrapontos,
            inconsistencias_temporais=inconsistencias,
            auditoria_matematica_valida=valido,
            justificativa_final="Revisão matemática e temporal concluída com sucesso."
            if valido
            else "Proposta reprovada pelos critérios de governança.",
        )

    def executar_ciclo_completo(self) -> Dict[str, Any]:
        """
        Executa o fluxo de ponta a ponta:
        1. Coleta -> 2. Análise -> 3. Revisão -> 4. Order Gate -> 5. Carteira
        """
        # 1. Coleta de dados
        caminho_snapshot = self.coletor.salvar_snapshot()
        with open(caminho_snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        # 2. Análise
        diagnostico = self.analisar_mercado_deterministico(snapshot)

        resultados_ciclo = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime_macro": diagnostico.regime_macro_vigente,
            "propostas_geradas": len(diagnostico.propostas),
            "decisoes": [],
            "saldo_final_carteira": self.carteira.saldo_caixa,
            "patrimonio_total": self.carteira.patrimonio_total,
        }

        # 3 e 4. Revisão e Order Gate
        for prop in diagnostico.propostas:
            metricas = snapshot.get(prop.ativo, {})
            revisao = self.revisar_proposta(prop, metricas)

            if revisao.parecer != ParecerRevisao.APROVADO:
                resultados_ciclo["decisoes"].append(
                    {
                        "ativo": prop.ativo,
                        "status": "REPROVADO_NA_REVISAO",
                        "motivo": revisao.contrapontos_identificados + revisao.inconsistencias_temporais,
                    }
                )
                continue

            # Submete ao OrderGate
            proposta_trade = PropostaTrade(
                proposta_id=f"PROP-{prop.ativo}",
                ativo=prop.ativo,
                tipo=TipoOperacao.COMPRA if prop.tipo_operacao == "COMPRA" else TipoOperacao.VENDA,
                preco_atual=prop.preco_referencia,
                preco_bid=prop.preco_referencia * 0.9995,
                preco_ask=prop.preco_referencia * 1.0005,
                preco_stop_loss=prop.preco_stop_loss,
                preco_take_profit=prop.preco_take_profit,
                probabilidade_sucesso=prop.probabilidade_estimada,
                vies_macro=prop.vies_macro.value,
                justificativa=prop.justificativa_quant,
            )

            decisao_gate = self.gate.avaliar_e_executar(proposta_trade)
            resultados_ciclo["decisoes"].append(
                {
                    "ativo": prop.ativo,
                    "autorizado": decisao_gate.autorizado,
                    "motivo": decisao_gate.motivo,
                    "lote": decisao_gate.dimensionamento.tamanho_lote if decisao_gate.dimensionamento else 0,
                    "risco_brl": decisao_gate.dimensionamento.risco_financeiro_brl
                    if decisao_gate.dimensionamento
                    else 0,
                }
            )

        resultados_ciclo["saldo_final_carteira"] = self.carteira.saldo_caixa
        resultados_ciclo["patrimonio_total"] = self.carteira.patrimonio_total
        return resultados_ciclo


if __name__ == "__main__":
    print("Iniciando ciclo de demonstração do núcleo mínimo...")
    coord = CoordenadorCiclo()
    res = coord.executar_ciclo_completo()
    print("\n=== Resultado do Ciclo ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
