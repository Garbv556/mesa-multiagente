"""
Módulo de Notificações e Comandos via Telegram.
Envia alertas em tempo real para o celular do operador e permite aprovar ordens
no modo "Sugestão + 1 Clique" diretamente pelo smartphone.
"""

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, List, Optional
import requests


@dataclass
class InfoTelegram:
    ativo: bool
    nome_bot: Optional[str]
    chat_id_configurado: bool
    detalhes: str


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def reconfigurar(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        os.environ["TELEGRAM_BOT_TOKEN"] = self.bot_token
        os.environ["TELEGRAM_CHAT_ID"] = self.chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def obter_status(self) -> InfoTelegram:
        if not self.bot_token or not self.chat_id:
            return InfoTelegram(
                ativo=False,
                nome_bot=None,
                chat_id_configurado=bool(self.chat_id),
                detalhes="Telegram não configurado. Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.",
            )

        try:
            res = requests.get(f"{self.base_url}/getMe", timeout=5)
            if res.ok:
                bot_info = res.json().get("result", {})
                nome = bot_info.get("first_name", "Bot")
                username = bot_info.get("username", "")
                return InfoTelegram(
                    ativo=True,
                    nome_bot=f"{nome} (@{username})",
                    chat_id_configurado=True,
                    detalhes=f"Conectado ao bot @{username}.",
                )
        except Exception as e:
            return InfoTelegram(
                ativo=False,
                nome_bot=None,
                chat_id_configurado=True,
                detalhes=f"Falha ao validar token no Telegram: {e}",
            )

        return InfoTelegram(
            ativo=False,
            nome_bot=None,
            chat_id_configurado=True,
            detalhes="Token inválido no Telegram.",
        )

    def enviar_mensagem(
        self,
        texto: str,
        botoes: Optional[List[List[Dict[str, str]]]] = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        url = f"{self.base_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": parse_mode,
        }

        if botoes:
            payload["reply_markup"] = {"inline_keyboard": botoes}

        try:
            res = requests.post(url, json=payload, timeout=8)
            return res.ok
        except Exception as e:
            print(f"[Aviso Telegram] Falha ao enviar mensagem: {e}")
            return False

    def notificar_proposta_trade(
        self,
        proposta: Dict[str, Any],
        url_painel: str = "https://mesa-multiagente-production.up.railway.app",
    ) -> bool:
        ativo = proposta.get("ativo", "N/A")
        tipo = proposta.get("tipo", "COMPRA")
        preco = proposta.get("preco_atual", 0.0)
        stop = proposta.get("preco_stop_loss", 0.0)
        alvo = proposta.get("preco_take_profit", 0.0)
        confianca = int(proposta.get("probabilidade", 0.78) * 100)
        justificativa = proposta.get("justificativa", "")
        revisor = proposta.get("revisor_parecer", "APROVADO")

        emoji_tipo = "🟢 COMPRA" if tipo == "COMPRA" else "🔴 VENDA"

        texto = (
            f"🚨 *Mesa Multiagente: Nova Proposta de Trade*\n\n"
            f"📊 *Ativo:* `{ativo}`\n"
            f"🎯 *Operação:* *{emoji_tipo}*\n"
            f"💵 *Preço Atual:* `R$ {preco:.2f}`\n"
            f"🛑 *Stop Loss (ATR):* `R$ {stop:.2f}`\n"
            f"🎯 *Take Profit:* `R$ {alvo:.2f}`\n"
            f"🧠 *Confiança IA:* `{confianca}%`\n"
            f"🛡️ *Revisor:* *{revisor}*\n\n"
            f"💡 *Tese:* _{justificativa}_\n\n"
            f"⚖️ _Para executar respeitando o Quarter-Kelly, acesse o painel abaixo:_"
        )

        botoes = [
            [
                {
                    "text": "📲 Abrir Painel e Aprovar",
                    "url": url_painel,
                }
            ]
        ]

        return self.enviar_mensagem(texto, botoes=botoes)

    def notificar_execucao(
        self,
        ativo: str,
        tipo: str,
        lote: float,
        preco: float,
        risco_brl: float,
        saldo_restante: float,
    ) -> bool:
        texto = (
            f"✅ *Ordem Executada pelo Order Gate*\n\n"
            f"📈 *Ativo:* `{ativo}` ({tipo})\n"
            f"📦 *Lote Fracionado:* `{lote:.4f}` cotas\n"
            f"💵 *Preço de Execução:* `R$ {preco:.2f}`\n"
            f"🛡️ *Risco Máximo Calculado:* `R$ {risco_brl:.2f}` (Trava <= 2%)\n"
            f"💰 *Saldo Disponível em Caixa:* `R$ {saldo_restante:.2f}`"
        )
        return self.enviar_mensagem(texto)
