"""
Notificador e Gerador de Relatórios via WhatsApp.
Permite o envio de relatórios quantitativos diários e alertas de trade
diretamente para o WhatsApp do operador.

Suporta:
- CallMeBot (Gateway gratuito e direto para WhatsApp pessoal, sem burocracia de Meta Business)
- Webhook Customizado (Evolution API, Z-API, Baileys ou Zapier/Make)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional
import urllib.parse
import requests


@dataclass
class StatusWhatsApp:
    ativo: bool
    modo: str  # "callmebot", "webhook", "nenhum"
    telefone: Optional[str]
    detalhes: str


class WhatsAppNotifier:
    def __init__(
        self,
        telefone: Optional[str] = None,
        apikey_callmebot: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        self.telefone = telefone or os.environ.get("WHATSAPP_PHONE")
        self.apikey_callmebot = apikey_callmebot or os.environ.get("WHATSAPP_CALLMEBOT_KEY")
        self.webhook_url = webhook_url or os.environ.get("WHATSAPP_WEBHOOK_URL")

    def reconfigurar(
        self,
        telefone: str,
        apikey_callmebot: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ) -> None:
        self.telefone = telefone.strip().replace("+", "").replace("-", "").replace(" ", "")
        self.apikey_callmebot = (apikey_callmebot or "").strip()
        self.webhook_url = (webhook_url or "").strip()

        os.environ["WHATSAPP_PHONE"] = self.telefone
        if self.apikey_callmebot:
            os.environ["WHATSAPP_CALLMEBOT_KEY"] = self.apikey_callmebot
        if self.webhook_url:
            os.environ["WHATSAPP_WEBHOOK_URL"] = self.webhook_url

    def obter_status(self) -> StatusWhatsApp:
        if self.telefone and self.apikey_callmebot:
            return StatusWhatsApp(
                ativo=True,
                modo="callmebot",
                telefone=self.telefone,
                detalhes=f"Conectado via CallMeBot para o número {self.telefone}.",
            )
        elif self.telefone and self.webhook_url:
            return StatusWhatsApp(
                ativo=True,
                modo="webhook",
                telefone=self.telefone,
                detalhes=f"Conectado via Webhook WhatsApp para {self.telefone}.",
            )
        return StatusWhatsApp(
            ativo=False,
            modo="nenhum",
            telefone=None,
            detalhes="WhatsApp não configurado. Defina o número e chave CallMeBot ou Webhook.",
        )

    def enviar_mensagem(self, texto: str) -> bool:
        status = self.obter_status()
        if not status.ativo or not self.telefone:
            print("[WhatsApp] Notificador inativo.")
            return False

        try:
            # Modo 1: CallMeBot (Gratuito e direto)
            if self.apikey_callmebot:
                texto_encoded = urllib.parse.quote(texto)
                url = f"https://api.callmebot.com/whatsapp.php?phone={self.telefone}&text={texto_encoded}&apikey={self.apikey_callmebot}"
                res = requests.get(url, timeout=12)
                return res.ok or "Message sent" in res.text or "queued" in res.text

            # Modo 2: Webhook Customizado (Evolution / Z-API)
            elif self.webhook_url:
                payload = {
                    "number": self.telefone,
                    "phone": self.telefone,
                    "message": texto,
                    "text": texto,
                }
                res = requests.post(self.webhook_url, json=payload, timeout=12)
                return res.ok
        except Exception as e:
            print(f"[Erro WhatsApp] Falha ao enviar mensagem: {e}")
            return False

        return False

    def enviar_relatorio_mercado(
        self,
        patrimonio_total: float,
        saldo_caixa: float,
        pnl_hoje: float,
        regime_macro: str,
        cotacoes: Dict[str, Any],
        provedor_ia: str = "Grok / Sistema 2",
    ) -> bool:
        agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
        
        linhas_ativos = []
        for ticker, dados in cotacoes.items():
            nome = dados.get("nome", ticker)
            preco = dados.get("preco_atual")
            if dados.get("disponivel") is False or not isinstance(preco, (int, float)):
                motivo = dados.get("aviso") or "fonte sem resposta"
                linhas_ativos.append(f"• *{ticker}* ({nome}): cotação indisponível ({motivo})")
                continue
            variacao = dados.get("variacao_dia_pct")
            if not isinstance(variacao, (int, float)):
                variacao = 0.0
            var = variacao * 100
            sinal = "+" if var >= 0 else ""
            zscore = dados.get("zscore_20p")
            z_txt = f"{zscore:.2f}" if isinstance(zscore, (int, float)) else "indisponível"
            prefixo = "US$ " if ticker == "^VIX" else "R$ "
            linhas_ativos.append(
                f"• *{ticker}* ({nome}): {prefixo}{preco:.2f} ({sinal}{var:.2f}%) | Z: {z_txt}"
            )

        bloco_ativos = "\n".join(linhas_ativos)

        mensagem = (
            f"📊 *RELATÓRIO MESA MULTIAGENTE*\n"
            f"🗓️ {agora}\n\n"
            f"💰 *Patrimônio:* R$ {patrimonio_total:.2f} (Meta: R$ 250,00)\n"
            f"💵 *Caixa Livre:* R$ {saldo_caixa:.2f}\n"
            f"📈 *P&L Hoje:* R$ {pnl_hoje:.2f}\n"
            f"🌐 *Regime Macro:* {regime_macro}\n"
            f"🧠 *Cérebro Ativo:* {provedor_ia}\n\n"
            f"🔍 *Cesta Multimercado & Distorções:*\n"
            f"{bloco_ativos}\n\n"
            f"🛡️ *Gestão de Risco:* Quarter-Kelly ativo (Risco máximo 2% por trade).\n"
            f"🔗 *Painel Cloud:* https://mesa-multiagente-production.up.railway.app"
        )

        return self.enviar_mensagem(mensagem)

    def notificar_proposta_whatsapp(self, proposta: Dict[str, Any]) -> bool:
        mensagem = (
            f"🚨 *NOVA OPORTUNIDADE IDENTIFICADA PELA IA*\n\n"
            f"🎯 *Ativo:* {proposta.get('ativo')}\n"
            f"📌 *Operação:* {proposta.get('tipo')}\n"
            f"💵 *Preço Referência:* R$ {proposta.get('preco_atual', 0.0):.2f}\n"
            f"🛑 *Stop Loss:* R$ {proposta.get('preco_stop_loss', 0.0):.2f}\n"
            f"🎯 *Take Profit:* R$ {proposta.get('preco_take_profit', 0.0):.2f}\n"
            f"🎲 *Probabilidade:* {(proposta.get('probabilidade', 0.0)*100):.0f}%\n"
            f"🔍 *Revisor:* {proposta.get('revisor_parecer', 'APROVADO')}\n\n"
            f"📝 *Tese Quant:* {proposta.get('justificativa', '')}\n\n"
            f"👉 *Aprovar ou Rejeitar em 1 Clique:*\n"
            f"https://mesa-multiagente-production.up.railway.app"
        )
        return self.enviar_mensagem(mensagem)
