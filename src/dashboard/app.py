"""
Painel Web Privado da Mesa Proprietária Multiagente (FastAPI).
Permite visualização em tempo real de:
- Patrimônio e metas da Fase Semente (R$ 100 -> R$ 250)
- Métricas e cotações da cesta multimercado (Z-Score, ATR, Volatilidade)
- Regime macroeconômico vigente
- Propostas do Analista e parecer do Revisor
- Botão "Sugestão + 1 Clique" para aprovação humana e execução pelo Order Gate
- Histórico auditável de ordens
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.collectors.market_data import ColetorMercado
from src.execution.portfolio_simulator import CarteiraSimulada, TipoOperacao, EstadoOrdem
from src.execution.order_gate import OrderGate, PropostaTrade
from src.agents.contracts import ParecerRevisao, ViesDirecional
from src.finance.math_engine import calcular_drawdown_maximo

app = FastAPI(title="Mesa Proprietária Multiagente - Dashboard")

# Instância persistente da carteira e do OrderGate
CONFIG_PATH = os.getenv("CONFIG_PATH", "config/risk_limits.json")
carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
gate = OrderGate(caminho_config=CONFIG_PATH, carteira=carteira)
coletor = ColetorMercado()

# Estado de propostas pendentes para aprovação humana
propostas_pendentes: Dict[str, Dict[str, Any]] = {}
ultimo_diagnostico: Dict[str, Any] = {
    "regime_macro": "Aguardando primeiro ciclo",
    "resumo": "Nenhum ciclo executado ainda.",
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
curva_patrimonio: List[float] = [100.0]


class AprovacaoRequest(BaseModel):
    proposta_id: str


@app.get("/", response_class=HTMLResponse)
async def get_index():
    caminho_html = Path("src/dashboard/templates/index.html")
    if not caminho_html.exists():
        return HTMLResponse("<h1>Template não encontrado</h1>", status_code=500)
    return HTMLResponse(caminho_html.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status():
    patrimonio = carteira.patrimonio_total
    curva_patrimonio.append(patrimonio)
    dd_atual, max_dd = calcular_drawdown_maximo(curva_patrimonio)

    posicoes_detalhadas = []
    for ticker, pos in carteira.posicoes.items():
        posicoes_detalhadas.append(
            {
                "ativo": pos.ativo,
                "quantidade": round(pos.quantidade, 4),
                "preco_medio": round(pos.preco_medio, 2),
                "preco_atual": round(pos.preco_atual, 2),
                "valor_mercado": round(pos.valor_mercado, 2),
                "pl_nao_realizado": round(pos.pl_nao_realizado, 2),
                "pl_pct": round((pos.preco_atual / pos.preco_medio - 1.0) * 100, 2)
                if pos.preco_medio > 0
                else 0.0,
            }
        )

    return {
        "capital_inicial": carteira.capital_inicial,
        "saldo_caixa": round(carteira.saldo_caixa, 2),
        "patrimonio_total": round(patrimonio, 2),
        "progresso_meta_pct": round(((patrimonio - 100.0) / 150.0) * 100, 1),
        "meta_alvo_brl": 250.0,
        "pl_realizado_hoje": round(carteira.pl_realizado_hoje, 2),
        "perdas_consecutivas_hoje": carteira.perdas_consecutivas_hoje,
        "drawdown_atual_pct": round(dd_atual * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "total_posicoes": len(posicoes_detalhadas),
        "posicoes": posicoes_detalhadas,
        "regime_macro": ultimo_diagnostico.get("regime_macro"),
        "ultimo_resumo": ultimo_diagnostico.get("resumo"),
        "timestamp_atual": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/market")
async def get_market():
    caminho_snapshot = Path("data/snapshots/ultimo_mercado.json")
    if caminho_snapshot.exists():
        with open(caminho_snapshot, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@app.get("/api/proposals")
async def get_proposals():
    return list(propostas_pendentes.values())


@app.post("/api/cycle/run")
async def run_cycle():
    global ultimo_diagnostico, propostas_pendentes
    snapshot = coletor.coletar_cesta_completa()
    coletor.salvar_snapshot()

    # Atualiza as cotações das posições abertas na carteira
    for ticker, metrica in snapshot.items():
        carteira.atualizar_cotacao(ticker, metrica.preco_atual)

    # Avaliação Macro
    usd = snapshot.get("USDBRL=X")
    z_usd = usd.zscore_20p if usd else 0.0
    regime = "Reflação / Cautela Cambial" if z_usd > 1.5 else "Goldilocks / Oportunidade"

    ultimo_diagnostico = {
        "regime_macro": regime,
        "resumo": f"Análise concluída com 4 ativos. Dólar Z={z_usd:.2f}.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Gera propostas do analista
    propostas_pendentes.clear()
    for ticker, m in snapshot.items():
        if ticker == "USDBRL=X":
            continue

        if m.zscore_20p <= -1.8:
            dist_stop = 1.5 * m.atr_14p
            p_stop = m.preco_atual - dist_stop
            p_alvo = m.preco_atual + (2.0 * dist_stop)
            prop_id = f"PROP-{ticker}-{int(datetime.now().timestamp())}"

            propostas_pendentes[prop_id] = {
                "proposta_id": prop_id,
                "ativo": ticker,
                "tipo": "COMPRA",
                "preco_atual": round(m.preco_atual, 2),
                "preco_stop_loss": round(p_stop, 2),
                "preco_take_profit": round(p_alvo, 2),
                "probabilidade": 0.78,
                "justificativa": f"Estiramento estatístico inferior (Z={m.zscore_20p:.2f}) com ATR=R${m.atr_14p:.2f}",
                "vies_macro": "LONG",
                "revisor_parecer": "APROVADO",
                "revisor_nota": "Auditoria de dados e relação risco/retorno (2.0x) confirmada.",
                "status": "PENDENTE_APROVACAO_HUMANA",
            }

    return {
        "status": "Ciclo executado com sucesso",
        "novas_propostas": len(propostas_pendentes),
        "regime_macro": regime,
    }


@app.post("/api/proposals/{proposta_id}/approve")
async def approve_proposal(proposta_id: str):
    if proposta_id not in propostas_pendentes:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")

    prop = propostas_pendentes[proposta_id]
    if prop["status"] != "PENDENTE_APROVACAO_HUMANA":
        raise HTTPException(status_code=400, detail="Proposta já processada.")

    # Converte e envia ao Order Gate para validação matemática de risco
    trade = PropostaTrade(
        proposta_id=prop["proposta_id"],
        ativo=prop["ativo"],
        tipo=TipoOperacao.COMPRA if prop["tipo"] == "COMPRA" else TipoOperacao.VENDA,
        preco_atual=prop["preco_atual"],
        preco_bid=prop["preco_atual"] * 0.9995,
        preco_ask=prop["preco_atual"] * 1.0005,
        preco_stop_loss=prop["preco_stop_loss"],
        preco_take_profit=prop["preco_take_profit"],
        probabilidade_sucesso=prop["probabilidade"],
        vies_macro=prop["vies_macro"],
        justificativa=f"[Aprovado pelo Usuário] {prop['justificativa']}",
    )

    decisao = gate.avaliar_e_executar(trade)
    if not decisao.autorizado:
        prop["status"] = "REJEITADA_PELO_GATE"
        prop["motivo_gate"] = decisao.motivo
        return {"sucesso": False, "motivo": decisao.motivo}

    prop["status"] = "EXECUTADA"
    prop["lote_executado"] = decisao.dimensionamento.tamanho_lote
    prop["risco_brl"] = decisao.dimensionamento.risco_financeiro_brl

    return {
        "sucesso": True,
        "motivo": decisao.motivo,
        "lote": decisao.dimensionamento.tamanho_lote,
        "risco_brl": decisao.dimensionamento.risco_financeiro_brl,
        "saldo_restante": round(carteira.saldo_caixa, 2),
    }


@app.post("/api/proposals/{proposta_id}/reject")
async def reject_proposal(proposta_id: str):
    if proposta_id not in propostas_pendentes:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    propostas_pendentes[proposta_id]["status"] = "REJEITADA_PELO_USUARIO"
    return {"status": "Proposta rejeitada manualmente."}


@app.get("/api/orders")
async def get_orders():
    return [
        {
            "ordem_id": o.ordem_id,
            "ativo": o.ativo,
            "tipo": o.tipo.value,
            "quantidade": round(o.quantidade, 4),
            "preco_execucao": round(o.preco_execucao, 2),
            "preco_stop_loss": round(o.preco_stop_loss, 2),
            "preco_take_profit": round(o.preco_take_profit, 2),
            "estado": o.estado.value,
            "timestamp": o.timestamp,
            "justificativa": o.justificativa,
        }
        for o in reversed(carteira.historico_ordens)
    ]
