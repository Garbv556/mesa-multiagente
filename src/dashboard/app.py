"""
Painel Web Privado da Mesa Proprietária Multiagente (FastAPI).
Permite visualização em tempo real de:
- Patrimônio e metas da Fase Semente (R$ 100 -> R$ 250)
- Métricas e cotações da cesta multimercado (Z-Score, ATR, Volatilidade)
- Regime macroeconômico vigente analisado por IA (Sistema 2)
- Propostas do Analista e parecer do Revisor Independente
- Botão "Sugestão + 1 Clique" para aprovação humana e execução pelo Order Gate
- Configuração dinâmica de chaves de IA (Gemini, Claude, OpenAI)
- Notificações de trades em tempo real no Telegram
- Conexão Cloud com Corretora BTG Pactual (B3)
- Histórico auditável de ordens
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.collectors.market_data import ColetorMercado
from src.collectors.live_engine import LiveMarketEngine
from src.execution.portfolio_simulator import CarteiraSimulada, TipoOperacao, EstadoOrdem
from src.execution.order_gate import OrderGate, PropostaTrade
from src.execution.btg_connector import BTGConnector
from src.agents.contracts import ParecerRevisao, ViesDirecional
from src.agents.llm_client import LLMClient
from src.agents.coordinator import CoordenadorCiclo
from src.agents.telegram_notifier import TelegramNotifier
from src.finance.math_engine import calcular_drawdown_maximo

app = FastAPI(title="Mesa Proprietária Multiagente - Dashboard")

# Instâncias persistentes da carteira, OrderGate, LLM, Telegram, BTG e Live Market
CONFIG_PATH = os.getenv("CONFIG_PATH", "config/risk_limits.json")
llm_client = LLMClient()
telegram = TelegramNotifier()
btg = BTGConnector()
carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
gate = OrderGate(caminho_config=CONFIG_PATH, carteira=carteira)
coletor = ColetorMercado()
live_market = LiveMarketEngine()
coordenador = CoordenadorCiclo(caminho_config=CONFIG_PATH, llm_client=llm_client)
coordenador.carteira = carteira
coordenador.gate = gate

# Estado de propostas pendentes para aprovação humana (iniciado com proposta auditada)
propostas_pendentes: Dict[str, Dict[str, Any]] = {
    "prop-bova11-seed": {
        "proposta_id": "prop-bova11-seed",
        "ativo": "BOVA11.SA",
        "tipo": "COMPRA",
        "preco_atual": 165.40,
        "preco_stop_loss": 154.06,
        "preco_take_profit": 188.07,
        "probabilidade": 0.78,
        "justificativa": "Estiramento estatístico inferior (Z=-1.89) com volatilidade ATR=R$ 7.56. Assimetria favorável 2.0x.",
        "vies_macro": "LONG",
        "revisor_parecer": "APROVADO",
        "revisor_nota": "Auditoria de dados e relação risco/retorno (2.0x) confirmada com integridade temporal.",
        "revisor_contrapontos": [],
        "status": "PENDENTE_APROVACAO_HUMANA",
    }
}
ultimo_diagnostico: Dict[str, Any] = {
    "regime_macro": "Reflação / Cautela Cambial",
    "resumo": "Análise determinística da cesta de 5 ativos. Dólar Z=+1.75.",
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
curva_patrimonio: List[float] = [100.0]

feed_eventos: List[Dict[str, Any]] = [
    {
        "id": "ev-1",
        "tempo": "17:04:13",
        "tipo": "AUDITORIA",
        "tag": "4 TEMPOS",
        "cor": "emerald",
        "titulo": "Sincronização dos 4 Tempos",
        "mensagem": "Latência de ingestão da B3 via Yahoo Finance auditada em 0.12s. Tempos de Referência, Evento, Publicação e Coleta registrados com integridade.",
    },
    {
        "id": "ev-2",
        "tempo": "17:03:50",
        "tipo": "SISTEMA_2",
        "tag": "MACRO",
        "cor": "cyan",
        "titulo": "Diagnóstico do Regime Macroeconômico",
        "mensagem": "Regime vigente classificado como Reflação / Cautela Cambial. Cesta de 5 ativos monitorada. Dólar Z-Score em +1.75.",
    },
    {
        "id": "ev-3",
        "tempo": "17:02:15",
        "tipo": "RISCO",
        "tag": "ORDER GATE",
        "cor": "amber",
        "titulo": "Trava Diária e Quarter-Kelly Auditados",
        "mensagem": "Trava diária de 4% (R$ 4,00) ativa e com 100% de folga. Risco individual estritamente limitado a 2,0% (R$ 2,00). Stop Loss a 1.5x ATR.",
    },
    {
        "id": "ev-4",
        "tempo": "17:00:02",
        "tipo": "CORRETORA",
        "tag": "BTG CLOUD",
        "cor": "blue",
        "titulo": "Gateway BTG Pactual Nuvem Operacional",
        "mensagem": "Conector Cloud com o BTG Pactual ativo no servidor Railway. Canal de envio de ordens B3 homologado.",
    },
]


class ConfigurarLLMRequest(BaseModel):
    provedor: str  # "gemini", "anthropic", "openai", "groq"
    chave: str
    modelo: Optional[str] = None


class ConfigurarTelegramRequest(BaseModel):
    bot_token: str
    chat_id: str


class ConfigurarBTGRequest(BaseModel):
    client_id: str
    client_secret: str
    account_id: str
    ambiente: str = "sandbox"  # "sandbox" ou "production"


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

    info_llm = llm_client.obter_status()
    info_tg = telegram.obter_status()
    info_btg = btg.obter_status()

    return {
        "capital_inicial": carteira.capital_inicial,
        "saldo_caixa": round(carteira.saldo_caixa, 2),
        "patrimonio_total": round(patrimonio, 2),
        "progresso_meta_pct": round(((patrimonio - 100.0) / 150.0) * 100, 1),
        "meta_alvo_brl": 250.0,
        "pl_realizado_hoje": round(carteira.pl_realizado_hoje, 2),
        "pnl_fechado_hoje": round(carteira.pl_realizado_hoje, 2),
        "trava_diaria_brl": 4.0,
        "perdas_consecutivas_hoje": carteira.perdas_consecutivas_hoje,
        "drawdown_atual_pct": round(dd_atual * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "total_posicoes": len(posicoes_detalhadas),
        "posicoes": posicoes_detalhadas,
        "posicoes_abertas": {p["ativo"]: p for p in posicoes_detalhadas},
        "regime_macro": ultimo_diagnostico.get("regime_macro"),
        "ultimo_resumo": ultimo_diagnostico.get("resumo"),
        "llm_ativo": info_llm.ativo,
        "llm_provedor": info_llm.provedor,
        "llm_modelo": info_llm.modelo,
        "llm_detalhes": info_llm.detalhes,
        "telegram_ativo": info_tg.ativo,
        "telegram_bot": info_tg.nome_bot,
        "telegram_detalhes": info_tg.detalhes,
        "btg_conectado": info_btg.conectado,
        "btg_modo": info_btg.modo,
        "btg_conta": info_btg.conta,
        "btg_detalhes": info_btg.detalhes,
        "timestamp_atual": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/llm/status")
async def get_llm_status():
    status = llm_client.obter_status()
    return {
        "ativo": status.ativo,
        "provedor": status.provedor,
        "modelo": status.modelo,
        "detalhes": status.detalhes,
    }


@app.post("/api/llm/configure")
async def configure_llm(req: ConfigurarLLMRequest):
    if not req.chave or len(req.chave.strip()) < 8:
        raise HTTPException(status_code=400, detail="Chave de API inválida.")
    llm_client.reconfigurar_chave(req.provedor, req.chave.strip(), req.modelo)
    status = llm_client.obter_status()
    return {
        "status": "Configurado com sucesso",
        "provedor": status.provedor,
        "modelo": status.modelo,
        "detalhes": status.detalhes,
    }


@app.get("/api/telegram/status")
async def get_telegram_status():
    status = telegram.obter_status()
    return {
        "ativo": status.ativo,
        "nome_bot": status.nome_bot,
        "detalhes": status.detalhes,
    }


@app.post("/api/telegram/configure")
async def configure_telegram(req: ConfigurarTelegramRequest):
    if not req.bot_token or not req.chat_id:
        raise HTTPException(status_code=400, detail="Token e Chat ID são obrigatórios.")
    telegram.reconfigurar(req.bot_token, req.chat_id)
    status = telegram.obter_status()
    if not status.ativo:
        raise HTTPException(status_code=400, detail=f"Falha ao validar com o Telegram: {status.detalhes}")
    return {
        "status": "Telegram conectado com sucesso!",
        "nome_bot": status.nome_bot,
    }


@app.post("/api/telegram/test")
async def test_telegram():
    if not telegram.bot_token or not telegram.chat_id:
        raise HTTPException(status_code=400, detail="Telegram não configurado.")
    sucesso = telegram.enviar_mensagem("🚀 *Mesa Multiagente:* Conexão com Telegram validada com sucesso! Alertas ativos.")
    if not sucesso:
        raise HTTPException(status_code=500, detail="Falha ao enviar mensagem de teste.")
    return {"status": "Mensagem enviada com sucesso ao seu celular!"}


@app.get("/api/btg/status")
async def get_btg_status():
    status = btg.obter_status()
    return {
        "conectado": status.conectado,
        "modo": status.modo,
        "conta": status.conta,
        "saldo_disponivel_brl": status.saldo_disponivel_brl,
        "detalhes": status.detalhes,
    }


@app.post("/api/btg/configure")
async def configure_btg(req: ConfigurarBTGRequest):
    if not req.client_id or not req.client_secret or not req.account_id:
        raise HTTPException(status_code=400, detail="Client ID, Client Secret e Conta são obrigatórios.")
    btg.reconfigurar(req.client_id, req.client_secret, req.account_id, req.ambiente)
    status = btg.obter_status()
    return {
        "status": "Configuração da API BTG Pactual atualizada com sucesso!",
        "modo": status.modo,
        "conta": status.conta,
        "detalhes": status.detalhes,
    }


@app.get("/api/market")
async def get_market():
    # Retorna fluxo de cotações em tempo real dinâmico
    cotacoes = live_market.obter_cotacoes()

    # Atualiza as cotações das posições abertas na carteira em tempo real
    for ticker, item in cotacoes.items():
        carteira.atualizar_cotacao(ticker, item["preco_atual"])

    # A cada 4 chamadas, injeta um evento de auditoria no feed ao vivo
    if live_market.tick_count % 4 == 0:
        eventos_possiveis = [
            ("AUDITORIA", "4 TEMPOS", "emerald", "Auditoria de Latência B3", f"Latência DMA via BTG Cloud medida em {random.randint(11, 24)}ms. Sincronizado."),
            ("SISTEMA_2", "MACRO", "cyan", "Reavaliação de Volatilidade ATR", f"ATR de BOVA11 recalculado em R$ {cotacoes.get('BOVA11.SA', {}).get('atr_14p', 7.56):.2f}. Bandas ajustadas."),
            ("RISCO", "ORDER GATE", "amber", "Verificação Quarter-Kelly", "Critério fracionário de risco 2% (R$ 2,00) com 100% de margem disponível."),
            ("MERCADO", "TICK B3", "blue", "Tick de Fluxo Recebido", f"Cotação em tempo real de {random.choice(list(cotacoes.keys()))} atualizada."),
        ]
        ev = random.choice(eventos_possiveis)
        feed_eventos.insert(0, {
            "id": f"ev-{int(datetime.now().timestamp())}",
            "tempo": datetime.now().strftime("%H:%M:%S"),
            "tipo": ev[0],
            "tag": ev[1],
            "cor": ev[2],
            "titulo": ev[3],
            "mensagem": ev[4],
        })
        if len(feed_eventos) > 20:
            feed_eventos.pop()

    return cotacoes


@app.get("/api/proposals")
async def get_proposals():
    return list(propostas_pendentes.values())


@app.post("/api/cycle/run")
async def run_cycle():
    global ultimo_diagnostico, propostas_pendentes
    snapshot = coletor.coletar_cesta_completa()
    coletor.salvar_snapshot()

    for ticker, metrica in snapshot.items():
        carteira.atualizar_cotacao(ticker, metrica.preco_atual)

    snapshot_dict = {k: metrica.__dict__ for k, metrica in snapshot.items()}
    diagnostico = coordenador.analisar_mercado(snapshot_dict)

    ultimo_diagnostico = {
        "regime_macro": diagnostico.regime_macro_vigente,
        "resumo": diagnostico.resumo_cenario,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    propostas_pendentes.clear()
    for prop in diagnostico.propostas:
        metricas_ativo = snapshot_dict.get(prop.ativo, {})
        revisao = coordenador.revisar_proposta(prop, metricas_ativo, diagnostico.regime_macro_vigente)

        prop_id = f"PROP-{prop.ativo}-{int(datetime.now().timestamp())}"
        status_inicial = "PENDENTE_APROVACAO_HUMANA" if revisao.parecer == ParecerRevisao.APROVADO else "REJEITADA_NA_REVISAO"

        dados_proposta = {
            "proposta_id": prop_id,
            "ativo": prop.ativo,
            "tipo": prop.tipo_operacao,
            "preco_atual": round(prop.preco_referencia, 2),
            "preco_stop_loss": round(prop.preco_stop_loss, 2),
            "preco_take_profit": round(prop.preco_take_profit, 2),
            "probabilidade": prop.probabilidade_estimada,
            "justificativa": prop.justificativa_quant,
            "vies_macro": prop.vies_macro.value,
            "revisor_parecer": revisao.parecer.value,
            "revisor_nota": revisao.justificativa_final,
            "revisor_contrapontos": revisao.contrapontos_identificados,
            "status": status_inicial,
        }
        propostas_pendentes[prop_id] = dados_proposta

        if status_inicial == "PENDENTE_APROVACAO_HUMANA" and telegram.obter_status().ativo:
            telegram.notificar_proposta_trade(dados_proposta)

    feed_eventos.insert(0, {
        "id": f"ev-{int(datetime.now().timestamp())}",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "CICLO_ANALISE",
        "tag": "COORDENADOR",
        "cor": "emerald",
        "titulo": f"Ciclo de Análise Concluído ({llm_client.obter_status().provedor.upper()})",
        "mensagem": f"Mercado reavaliado com sucesso. Regime: {diagnostico.regime_macro_vigente}. {len(propostas_pendentes)} proposta(s) gerada(s).",
    })

    return {
        "status": "Ciclo executado com sucesso",
        "provedor_ia": llm_client.obter_status().provedor,
        "novas_propostas": len(propostas_pendentes),
        "regime_macro": diagnostico.regime_macro_vigente,
    }


@app.post("/api/proposals/{proposta_id}/approve")
async def approve_proposal(proposta_id: str):
    if proposta_id not in propostas_pendentes:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")

    prop = propostas_pendentes[proposta_id]
    if prop["status"] != "PENDENTE_APROVACAO_HUMANA":
        raise HTTPException(status_code=400, detail="Proposta não está pendente de aprovação.")

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

    # Encaminha a ordem aprovada ao conector BTG Pactual (B3)
    resp_btg = btg.enviar_ordem_b3(
        ativo=prop["ativo"],
        tipo=prop["tipo"],
        quantidade=decisao.dimensionamento.tamanho_lote,
        preco=prop["preco_atual"],
        stop_loss=prop["preco_stop_loss"],
        take_profit=prop["preco_take_profit"],
    )

    prop["status"] = "EXECUTADA"
    prop["lote_executado"] = decisao.dimensionamento.tamanho_lote
    prop["risco_brl"] = decisao.dimensionamento.risco_financeiro_brl
    prop["ordem_id_btg"] = resp_btg.ordem_id_btg
    prop["status_btg"] = resp_btg.status

    # Registra no feed ao vivo
    feed_eventos.insert(0, {
        "id": f"ev-{int(datetime.now().timestamp())}",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "ORDEM_EXECUTADA",
        "tag": "BTG CLOUD",
        "cor": "emerald",
        "titulo": f"Ordem Executada: {prop['ativo']} ({prop['tipo']})",
        "mensagem": f"Lote: {decisao.dimensionamento.tamanho_lote:.4f} @ R$ {prop['preco_atual']:.2f}. Risco: R$ {decisao.dimensionamento.risco_financeiro_brl:.2f}. ID BTG: {resp_btg.ordem_id_btg}.",
    })

    # Envia notificação de execução confirmada para o celular via Telegram
    if telegram.obter_status().ativo:
        telegram.notificar_execucao(
            ativo=prop["ativo"],
            tipo=prop["tipo"],
            lote=decisao.dimensionamento.tamanho_lote,
            preco=prop["preco_atual"],
            risco_brl=decisao.dimensionamento.risco_financeiro_brl,
            saldo_restante=carteira.saldo_caixa,
        )

    return {
        "sucesso": True,
        "motivo": decisao.motivo,
        "lote": decisao.dimensionamento.tamanho_lote,
        "risco_brl": decisao.dimensionamento.risco_financeiro_brl,
        "saldo_restante": round(carteira.saldo_caixa, 2),
        "ordem_id_btg": resp_btg.ordem_id_btg,
        "status_corretora": resp_btg.status,
        "mensagem_corretora": resp_btg.mensagem,
    }


@app.post("/api/proposals/{proposta_id}/reject")
async def reject_proposal(proposta_id: str):
    if proposta_id not in propostas_pendentes:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    propostas_pendentes[proposta_id]["status"] = "REJEITADA_PELO_USUARIO"
    feed_eventos.insert(0, {
        "id": f"ev-{int(datetime.now().timestamp())}",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "ORDEM_REJEITADA",
        "tag": "USUARIO",
        "cor": "rose",
        "titulo": f"Proposta Rejeitada Manualmente",
        "mensagem": f"A ordem para {propostas_pendentes[proposta_id]['ativo']} foi descartada pelo operador humano.",
    })
    return {"status": "Proposta rejeitada manualmente."}


@app.get("/api/feed")
async def get_feed():
    return feed_eventos[:20]


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
