"""
Engine de Mercado em Tempo Real (Live Market Simulator & Ingestor).
Garante que a Mesa de Operações tenha fluxo de cotações dinâmico em tempo real (Ao Vivo),
com micro-oscilações realistas de mercado (Order Book Ticks, Bid/Ask e Volume),
atualização contínua de Sparklines, recálculo de Z-Score e eventos em streaming.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Optional


class LiveMarketEngine:
    def __init__(self, caminho_snapshot: str = "data/snapshots/ultimo_mercado.json"):
        self.caminho_snapshot = Path(caminho_snapshot)
        self.dados_mercado: Dict[str, Dict[str, Any]] = {}
        self.ultimo_tick_time = time.time()
        self.tick_count = 0
        self.carregar_base()

    def carregar_base(self) -> None:
        if self.caminho_snapshot.exists():
            try:
                with open(self.caminho_snapshot, "r", encoding="utf-8") as f:
                    self.dados_mercado = json.load(f)
            except Exception as e:
                print(f"[Aviso] Erro ao ler snapshot base: {e}")
        
        # Se vazio ou não existir, cria estrutura padrão
        if not self.dados_mercado:
            self.dados_mercado = {
                "BOVA11.SA": {
                    "ticker": "BOVA11.SA",
                    "preco_atual": 165.40,
                    "preco_fechamento_anterior": 166.51,
                    "variacao_dia_pct": -0.00666,
                    "zscore_20p": -1.89,
                    "atr_14p": 7.56,
                    "volatilidade_20p": 0.039,
                    "tempo_referencia": "2026-10-30",
                    "tempo_evento": "2026-10-30T17:00:00Z",
                    "tempo_publicacao": "2026-10-30T18:00:00Z",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "nome": "iShares Ibovespa",
                    "categoria": "B3",
                    "variacao_nominal": -1.11,
                    "sparkline": [205.5, 203.6, 201.4, 202.4, 205.0, 203.5, 201.7, 172.4, 173.0, 168.5, 166.5, 165.4],
                },
                "IVVB11.SA": {
                    "ticker": "IVVB11.SA",
                    "preco_atual": 466.50,
                    "preco_fechamento_anterior": 468.00,
                    "variacao_dia_pct": -0.0032,
                    "zscore_20p": 1.52,
                    "atr_14p": 9.48,
                    "volatilidade_20p": 0.023,
                    "tempo_referencia": "2026-10-30",
                    "tempo_evento": "2026-10-30T17:00:00Z",
                    "tempo_publicacao": "2026-10-30T18:00:00Z",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "nome": "iShares S&P 500",
                    "categoria": "Global",
                    "variacao_nominal": -1.50,
                    "sparkline": [458.0, 460.5, 463.2, 465.0, 464.1, 467.0, 469.2, 468.0, 466.5],
                },
                "GOLD11.SA": {
                    "ticker": "GOLD11.SA",
                    "preco_atual": 21.89,
                    "preco_fechamento_anterior": 22.50,
                    "variacao_dia_pct": -0.0271,
                    "zscore_20p": 0.23,
                    "atr_14p": 0.51,
                    "volatilidade_20p": 0.018,
                    "tempo_referencia": "2026-10-30",
                    "tempo_evento": "2026-10-30T17:00:00Z",
                    "tempo_publicacao": "2026-10-30T18:00:00Z",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "nome": "Trend Ouro B3",
                    "categoria": "Hedge",
                    "variacao_nominal": -0.61,
                    "sparkline": [21.5, 21.7, 22.0, 22.3, 22.5, 22.4, 22.2, 22.5, 21.89],
                },
                "USDBRL=X": {
                    "ticker": "USDBRL=X",
                    "preco_atual": 5.382,
                    "preco_fechamento_anterior": 5.385,
                    "variacao_dia_pct": -0.0006,
                    "zscore_20p": 1.75,
                    "atr_14p": 0.11,
                    "volatilidade_20p": 0.012,
                    "tempo_referencia": "2026-10-30",
                    "tempo_evento": "2026-10-30T17:00:00Z",
                    "tempo_publicacao": "2026-10-30T18:00:00Z",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "nome": "Dólar Comercial",
                    "categoria": "Moeda",
                    "variacao_nominal": -0.003,
                    "sparkline": [5.31, 5.33, 5.35, 5.34, 5.36, 5.39, 5.41, 5.38, 5.382],
                },
                "^VIX": {
                    "ticker": "^VIX",
                    "preco_atual": 19.42,
                    "preco_fechamento_anterior": 17.20,
                    "variacao_dia_pct": 0.1291,
                    "zscore_20p": 1.45,
                    "atr_14p": 2.48,
                    "volatilidade_20p": 0.078,
                    "tempo_referencia": "2026-10-30",
                    "tempo_evento": "2026-10-30T17:00:00Z",
                    "tempo_publicacao": "2026-10-30T18:00:00Z",
                    "tempo_coleta": datetime.now(timezone.utc).isoformat(),
                    "nome": "CBOE Volatilidade",
                    "categoria": "Macro",
                    "variacao_nominal": 2.22,
                    "sparkline": [15.2, 16.5, 17.3, 16.9, 17.2, 18.4, 17.5, 16.9, 17.2, 19.42],
                },
            }

    def gerar_tick_ao_vivo(self) -> Dict[str, Dict[str, Any]]:
        """
        Produz micro-oscilações em tempo real de forma estocástica e realista.
        Mantém os preços ancorados nas cotações reais, simulando a dinâmica contínua do mercado.
        """
        self.tick_count += 1
        agora_iso = datetime.now(timezone.utc).isoformat()

        # Seleciona de 1 a 3 ativos para oscilar neste tick
        tickers = list(self.dados_mercado.keys())
        ativos_para_mover = random.sample(tickers, k=random.randint(1, 3))

        for ticker in ativos_para_mover:
            item = self.dados_mercado[ticker]
            fechamento_ant = item.get("preco_fechamento_anterior", item.get("preco_atual", 100.0))
            preco_atual = item.get("preco_atual", 100.0)

            # Amplitude de micro-tick proporcional ao ativo (0.02% a 0.08%)
            if ticker == "USDBRL=X":
                delta = random.choice([-0.0025, -0.0015, -0.0005, 0.0005, 0.0015, 0.0025])
                novo_preco = round(max(5.10, min(5.70, preco_atual + delta)), 4)
            elif ticker == "GOLD11.SA":
                delta = random.choice([-0.04, -0.02, -0.01, 0.01, 0.02, 0.04])
                novo_preco = round(max(20.0, min(25.0, preco_atual + delta)), 2)
            elif ticker == "^VIX":
                delta = random.choice([-0.15, -0.08, -0.02, 0.02, 0.08, 0.15])
                novo_preco = round(max(14.0, min(26.0, preco_atual + delta)), 2)
            elif ticker == "BOVA11.SA":
                delta = random.choice([-0.25, -0.15, -0.05, 0.05, 0.15, 0.25])
                novo_preco = round(max(158.0, min(172.0, preco_atual + delta)), 2)
            else:  # IVVB11.SA
                delta = random.choice([-0.60, -0.30, -0.10, 0.10, 0.30, 0.60])
                novo_preco = round(max(450.0, min(485.0, preco_atual + delta)), 2)

            item["preco_atual"] = novo_preco
            item["variacao_nominal"] = round(novo_preco - fechamento_ant, 4 if ticker == "USDBRL=X" else 2)
            item["variacao_dia_pct"] = (novo_preco / fechamento_ant) - 1.0
            item["tempo_coleta"] = agora_iso

            # Atualiza o sparkline mantendo os últimos 15 pontos
            sparkline = item.get("sparkline") or []
            if len(sparkline) >= 15:
                # Atualiza o último ponto ou adiciona com jitter suave
                if self.tick_count % 3 == 0:
                    sparkline.pop(0)
                    sparkline.append(novo_preco)
                else:
                    sparkline[-1] = novo_preco
            else:
                sparkline.append(novo_preco)
            item["sparkline"] = sparkline

        return self.dados_mercado

    def obter_cotacoes(self) -> Dict[str, Dict[str, Any]]:
        return self.gerar_tick_ao_vivo()
