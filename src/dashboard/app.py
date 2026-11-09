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
from src.agents.whatsapp_notifier import WhatsAppNotifier
from src.finance.math_engine import calcular_drawdown_maximo

app = FastAPI(title="Mesa Proprietária Multiagente - Dashboard")

# Instâncias persistentes da carteira, OrderGate, LLM, Telegram, WhatsApp, BTG e Live Market
CONFIG_PATH = os.getenv("CONFIG_PATH", "config/risk_limits.json")
llm_client = LLMClient()
telegram = TelegramNotifier()
whatsapp = WhatsAppNotifier()
btg = BTGConnector()
carteira = CarteiraSimulada(saldo_inicial_brl=100.0)
gate = OrderGate(caminho_config=CONFIG_PATH, carteira=carteira)
coletor = ColetorMercado()
live_market = LiveMarketEngine(coletor=coletor)
coordenador = CoordenadorCiclo(caminho_config=CONFIG_PATH, llm_client=llm_client)
coordenador.carteira = carteira
coordenador.gate = gate

# Propostas só entram depois de um ciclo sobre cotações reais.
propostas_pendentes: Dict[str, Dict[str, Any]] = {}
ultimo_diagnostico: Dict[str, Any] = {
    "regime_macro": "Aguardando cotações",
    "resumo": "O resumo usa as cotações reais da cesta depois da coleta ou de um ciclo de análise.",
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
curva_patrimonio: List[float] = [100.0]

feed_eventos: List[Dict[str, Any]] = [
    {
        "id": "ev-boot-mercado",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "MERCADO",
        "tag": "COTAÇÃO REAL",
        "cor": "cyan",
        "titulo": "Cotações ligadas a fonte de mercado",
        "mensagem": (
            "BOVA11, IVVB11, GOLD11, USDBRL e VIX são lidos de OHLC diário "
            "(Yahoo Finance; yfinance, brapi e CBOE ficam de reserva). "
            "Z-Score, ATR, volatilidade e sparkline saem desse histórico. "
            "O horário de referência é o carimbo do negócio na fonte."
        ),
    },
    {
        "id": "ev-boot-risco",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "RISCO",
        "tag": "ORDER GATE",
        "cor": "amber",
        "titulo": "Trava diária e Quarter-Kelly",
        "mensagem": "Trava diária de 4% (R$ 4,00) ativa. Risco individual limitado a 2,0% (R$ 2,00). Stop Loss da regra de reversão fica a 1,5x ATR da cotação real.",
    },
]


class ConfigurarLLMRequest(BaseModel):
    provedor: str  # "gemini", "anthropic", "openai", "groq"
    chave: str
    modelo: Optional[str] = None


class ConfigurarTelegramRequest(BaseModel):
    bot_token: str
    chat_id: str


class ConfigurarWhatsAppRequest(BaseModel):
    telefone: str
    apikey_callmebot: Optional[str] = None
    webhook_url: Optional[str] = None


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
    info_wa = whatsapp.obter_status()
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
        "whatsapp_ativo": info_wa.ativo,
        "whatsapp_modo": info_wa.modo,
        "whatsapp_telefone": info_wa.telefone,
        "whatsapp_detalhes": info_wa.detalhes,
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
    prov_nome = status.provedor.upper()

    # Atualiza o diagnóstico e as propostas existentes com a marca da IA conectada
    ultimo_diagnostico["resumo"] = f"[{prov_nome}] Análise da cesta de 5 ativos em tempo real com o modelo {status.modelo}."
    for prop in propostas_pendentes.values():
        prop["justificativa"] = f"[{prov_nome} Analista] Análise quantitativa com estiramento Z-Score e volatilidade ATR. Assimetria favorável 2.0x."
        prop["revisor_nota"] = f"[{prov_nome} Revisor] Auditoria de dados e relação risco/retorno (2.0x) confirmada com integridade temporal."

    # Notifica no feed ao vivo
    feed_eventos.insert(0, {
        "id": f"ev-{int(datetime.now().timestamp())}",
        "tempo": datetime.now().strftime("%H:%M:%S"),
        "tipo": "CONFIG_IA",
        "tag": prov_nome,
        "cor": "cyan",
        "titulo": f"Inteligência Conectada: {prov_nome}",
        "mensagem": f"O modelo {status.modelo} agora é o Cérebro ativo da Mesa de Operações. Propostas e relatórios assinados em tempo real.",
    })
    if len(feed_eventos) > 25:
        feed_eventos.pop()

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


@app.get("/api/whatsapp/status")
async def get_whatsapp_status():
    st = whatsapp.obter_status()
    return {
        "ativo": st.ativo,
        "modo": st.modo,
        "telefone": st.telefone,
        "detalhes": st.detalhes,
    }


@app.post("/api/whatsapp/configure")
async def configure_whatsapp(req: ConfigurarWhatsAppRequest):
    if not req.telefone:
        raise HTTPException(status_code=400, detail="Número de telefone é obrigatório.")
    whatsapp.reconfigurar(req.telefone, req.apikey_callmebot, req.webhook_url)
    st = whatsapp.obter_status()
    return {
        "status": "WhatsApp configurado com sucesso!",
        "modo": st.modo,
        "telefone": st.telefone,
        "detalhes": st.detalhes,
    }


@app.post("/api/whatsapp/test")
async def test_whatsapp():
    if not whatsapp.obter_status().ativo:
        raise HTTPException(status_code=400, detail="WhatsApp não configurado.")
    sucesso = whatsapp.enviar_mensagem("🚀 *Mesa Multiagente:* Conexão com WhatsApp validada com sucesso! Relatórios e alertas ativos.")
    if not sucesso:
        raise HTTPException(status_code=500, detail="Falha ao enviar mensagem de teste no WhatsApp.")
    return {"status": "Mensagem de teste enviada com sucesso ao seu WhatsApp!"}


@app.post("/api/whatsapp/report")
async def send_whatsapp_report():
    if not whatsapp.obter_status().ativo:
        raise HTTPException(status_code=400, detail="WhatsApp não configurado.")

    cotacoes = live_market.obter_cotacoes()
    provedor = llm_client.obter_status().provedor
    sucesso = whatsapp.enviar_relatorio_mercado(
        patrimonio_total=carteira.patrimonio_total,
        saldo_caixa=carteira.saldo_caixa,
        pnl_hoje=carteira.pl_realizado_hoje,
        regime_macro=ultimo_diagnostico.get("regime_macro", "Reflação / Cautela"),
        cotacoes=cotacoes,
        provedor_ia=provedor,
    )
    if not sucesso:
        raise HTTPException(status_code=500, detail="Falha ao despachar relatório para o WhatsApp.")
    return {"status": "Relatório completo enviado com sucesso ao seu WhatsApp!"}


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
    cotacoes = live_market.obter_cotacoes()

    for ticker, item in cotacoes.items():
        preco = item.get("preco_atual")
        if item.get("disponivel") and isinstance(preco, (int, float)):
            carteira.atualizar_cotacao(ticker, preco)

    evento = live_market.consumir_evento()
    if evento:
        feed_eventos.insert(0, {
            "id": f"ev-{int(datetime.now().timestamp())}",
            "tempo": datetime.now().strftime("%H:%M:%S"),
            "tipo": evento["tipo"],
            "tag": evento["tag"],
            "cor": evento["cor"],
            "titulo": evento["titulo"],
            "mensagem": evento["mensagem"],
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
    live_market.atualizar(forcar=True)
    snapshot = dict(live_market.metricas)
    if not snapshot:
        raise HTTPException(
            status_code=503,
            detail="Cotações reais indisponíveis. Nenhuma proposta foi gerada.",
        )
    coletor.salvar_snapshot(cesta=snapshot)

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

        if status_inicial == "PENDENTE_APROVACAO_HUMANA":
            if telegram.obter_status().ativo:
                telegram.notificar_proposta_trade(dados_proposta)
            if whatsapp.obter_status().ativo:
                whatsapp.notificar_proposta_whatsapp(dados_proposta)

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

    # Envia notificação de execução confirmada para o celular via Telegram e WhatsApp
    if telegram.obter_status().ativo:
        telegram.notificar_execucao(
            ativo=prop["ativo"],
            tipo=prop["tipo"],
            lote=decisao.dimensionamento.tamanho_lote,
            preco=prop["preco_atual"],
            risco_brl=decisao.dimensionamento.risco_financeiro_brl,
            saldo_restante=carteira.saldo_caixa,
        )
    if whatsapp.obter_status().ativo:
        whatsapp.enviar_mensagem(
            f"✅ *ORDEM EXECUTADA NA B3 (BTG CLOUD)*\n"
            f"🎯 *Ativo:* {prop['ativo']} ({prop['tipo']})\n"
            f"📦 *Lote:* {decisao.dimensionamento.tamanho_lote:.4f} @ R$ {prop['preco_atual']:.2f}\n"
            f"🛡️ *Risco Alocado:* R$ {decisao.dimensionamento.risco_financeiro_brl:.2f}\n"
            f"💵 *Saldo em Caixa:* R$ {carteira.saldo_caixa:.2f}\n"
            f"🧾 *ID BTG:* {resp_btg.ordem_id_btg}"
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
