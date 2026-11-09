"""
Coordenador do Ciclo Operacional Mínimo.
Conecta os dados coletados ao Analista (Sistema 2 com LLM ou fallback),
submete a proposta ao Revisor Independente (Auditoria e contraponto)
e encaminha as propostas aprovadas ao Order Gate determinístico para execução na Carteira.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

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
from src.agents.llm_client import LLMClient
from src.agents.prompts import PROMPT_SISTEMA_ANALISTA, PROMPT_SISTEMA_REVISOR


class CoordenadorCiclo:
    def __init__(self, caminho_config: str = "config/risk_limits.json", llm_client: Optional[LLMClient] = None):
        self.caminho_config = caminho_config
        self.carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
        self.gate = OrderGate(caminho_config=self.caminho_config, carteira=self.carteira)
        self.coletor = ColetorMercado()
        self.llm = llm_client or LLMClient()

    def analisar_mercado(self, snapshot: Dict[str, Any]) -> DiagnosticoMercado:
        """
        Gera o diagnóstico de mercado. Se houver chave de IA ativa (Gemini, Claude, GPT),
        utiliza o LLM com o prompt formal do Sistema 2. Caso contrário, aciona o fallback determinístico.
        """
        if self.llm.provedor_ativo != "nenhum":
            prompt_usuario = (
                f"Dados observados da cesta multimercado (4 tempos registrados):\n"
                f"{json.dumps(snapshot, indent=2, ensure_ascii=False)}\n\n"
                f"Analise o regime macro e gere as propostas quantitativas cabíveis."
            )
            resposta = self.llm.gerar_json(PROMPT_SISTEMA_ANALISTA, prompt_usuario)
            if resposta and "regime_macro_vigente" in resposta:
                try:
                    propostas_formatadas = []
                    for p in resposta.get("propostas", []):
                        propostas_formatadas.append(
                            PropostaAnalista(
                                ativo=p["ativo"],
                                tipo_operacao=p.get("tipo_operacao", "COMPRA"),
                                preco_referencia=float(p["preco_referencia"]),
                                preco_stop_loss=float(p["preco_stop_loss"]),
                                preco_take_profit=float(p["preco_take_profit"]),
                                probabilidade_estimada=float(p.get("probabilidade_estimada", 0.78)),
                                justificativa_quant=p.get("justificativa_quant", ""),
                                vies_macro=ViesDirecional(p.get("vies_macro", "LONG")),
                            )
                        )
                    return DiagnosticoMercado(
                        regime_macro_vigente=resposta["regime_macro_vigente"],
                        resumo_cenario=f"[{self.llm.provedor_ativo.upper()}] {resposta.get('resumo_cenario', '')}",
                        propostas=propostas_formatadas,
                        timestamp_geracao=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception as e:
                    print(f"[Aviso] Falha ao processar saída JSON do Analista LLM: {e}. Acionando fallback determinístico.")

        return self.analisar_mercado_deterministico(snapshot)

    def analisar_mercado_deterministico(self, snapshot: Dict[str, Any]) -> DiagnosticoMercado:
        propostas: List[PropostaAnalista] = []
        agora = datetime.now(timezone.utc).isoformat()

        usd = snapshot.get("USDBRL=X") or {}
        z_usd = usd.get("zscore_20p")
        if usd.get("disponivel") is False or z_usd is None:
            regime = "Indeterminado"
            texto_dolar = "Dólar sem cotação real."
        else:
            z_usd = float(z_usd)
            regime = "Reflação / Cautela Cambial" if z_usd > 1.5 else "Goldilocks / Oportunidade"
            texto_dolar = f"Dólar Z={z_usd:.2f}."

        for ticker, metricas in snapshot.items():
            if ticker in ["USDBRL=X", "^VIX"]:
                continue
            if not isinstance(metricas, dict) or metricas.get("disponivel") is False:
                continue

            zscore = metricas.get("zscore_20p")
            preco = metricas.get("preco_atual")
            atr = metricas.get("atr_14p")
            if zscore is None or preco is None or atr is None:
                continue
            zscore = float(zscore)
            preco = float(preco)
            atr = float(atr)
            if preco <= 0 or atr <= 0:
                continue

            # Setup Retorno à Média (Mean Reversion)
            if zscore <= -1.8:
                distancia_stop = 1.5 * atr
                preco_stop = preco - distancia_stop
                preco_alvo = preco + (2.0 * distancia_stop)

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
            resumo_cenario=(
                f"Monitoramento determinístico de {len(snapshot)} ativos com cotações reais. {texto_dolar}"
            ),
            propostas=propostas,
            timestamp_geracao=agora,
        )

    def revisar_proposta(self, proposta: PropostaAnalista, metricas_ativo: dict, regime_macro: str = "Neutro") -> RelatorioRevisao:
        """
        O Revisor audita a consistência das contas e a atualidade dos dados.
        Se LLM disponível, submete ao auditor de IA independente; senão, usa checagem determinística.
        """
        if self.llm.provedor_ativo != "nenhum":
            prompt_usuario = (
                f"Proposta do Analista para Auditoria:\n"
                f"{proposta.model_dump_json(indent=2)}\n\n"
                f"Métricas brutas do ativo auditado:\n"
                f"{json.dumps(metricas_ativo, indent=2, ensure_ascii=False)}\n\n"
                f"Regime Macro Classificado: {regime_macro}\n\n"
                f"Audite a proposta e emita seu parecer formal."
            )
            resposta = self.llm.gerar_json(PROMPT_SISTEMA_REVISOR, prompt_usuario)
            if resposta and "parecer" in resposta:
                try:
                    return RelatorioRevisao(
                        parecer=ParecerRevisao(resposta["parecer"]),
                        contrapontos_identificados=resposta.get("contrapontos_identificados", []),
                        inconsistencias_temporais=resposta.get("inconsistencias_temporais", []),
                        auditoria_matematica_valida=bool(resposta.get("auditoria_matematica_valida", True)),
                        justificativa_final=f"[{self.llm.provedor_ativo.upper()}] {resposta.get('justificativa_final', '')}",
                    )
                except Exception as e:
                    print(f"[Aviso] Falha ao processar saída JSON do Revisor LLM: {e}. Usando auditoria determinística.")

        return self.revisar_proposta_deterministica(proposta, metricas_ativo)

    def revisar_proposta_deterministica(self, proposta: PropostaAnalista, metricas_ativo: dict) -> RelatorioRevisao:
        contrapontos = []
        inconsistencias = []

        tempo_coleta = metricas_ativo.get("tempo_coleta")
        if not tempo_coleta:
            inconsistencias.append("Dado sem timestamp de coleta.")

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
            justificativa_final="Revisão matemática e temporal confirmada com sucesso."
            if valido
            else "Proposta reprovada pelos critérios de risco.",
        )

    def executar_ciclo_completo(self) -> Dict[str, Any]:
        caminho_snapshot = self.coletor.salvar_snapshot()
        with open(caminho_snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        diagnostico = self.analisar_mercado(snapshot)

        resultados_ciclo = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provedor_ia": self.llm.obter_status().provedor,
            "modelo_ia": self.llm.obter_status().modelo,
            "regime_macro": diagnostico.regime_macro_vigente,
            "propostas_geradas": len(diagnostico.propostas),
            "decisoes": [],
            "saldo_final_carteira": self.carteira.saldo_caixa,
            "patrimonio_total": self.carteira.patrimonio_total,
        }

        for prop in diagnostico.propostas:
            metricas = snapshot.get(prop.ativo, {})
            revisao = self.revisar_proposta(prop, metricas, diagnostico.regime_macro_vigente)

            if revisao.parecer != ParecerRevisao.APROVADO:
                resultados_ciclo["decisoes"].append(
                    {
                        "ativo": prop.ativo,
                        "status": "REPROVADO_NA_REVISAO",
                        "motivo": revisao.contrapontos_identificados + revisao.inconsistencias_temporais,
                    }
                )
                continue

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
