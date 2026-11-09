"""
Cache das cotações reais servidas em /api/market.

Este módulo não gera micro-oscilação, não sorteia preço e não mantém um
pregão sintético. Ele só repete a última coleta real dentro do TTL e, se a
fonte falhar, reapresenta essa coleta marcada como desatualizada até expirar.
Sem coleta real dentro da validade, o ativo volta indisponível.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional

from src.collectors.market_data import METADADOS_ATIVOS, TICKERS_CESTA, ColetorMercado
from src.collectors.market_sources import FONTES_REAIS


def _parse_iso(valor: Any) -> Optional[datetime]:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


def _idade_segundos(valor: Any) -> Optional[float]:
    instante = _parse_iso(valor)
    if instante is None:
        return None
    return (datetime.now(timezone.utc) - instante).total_seconds()


class LiveMarketEngine:
    def __init__(
        self,
        coletor: Optional[ColetorMercado] = None,
        caminho_snapshot: str = "data/snapshots/ultimo_mercado.json",
        ttl_segundos: Optional[int] = None,
        validade_stale_segundos: Optional[int] = None,
    ):
        self.coletor = coletor or ColetorMercado()
        self.caminho_snapshot = Path(caminho_snapshot)
        self.tickers = list(getattr(self.coletor, "tickers", None) or TICKERS_CESTA)
        self.ttl = self._ler_inteiro(ttl_segundos, "MARKET_CACHE_TTL_SECONDS", 60)
        self.validade_stale = self._ler_inteiro(
            validade_stale_segundos, "MARKET_STALE_MAX_SECONDS", 129600
        )
        self.resposta: Dict[str, Dict[str, Any]] = {}
        self.metricas: Dict[str, Any] = {}
        self.dados_mercado = self.resposta
        self.evento_pendente: Optional[Dict[str, str]] = None
        self._lock = threading.Lock()
        self._em_coleta = False
        self._ultima_tentativa = 0.0
        self._carregar_cache_real()
        self.dados_mercado = self.resposta

    @staticmethod
    def _ler_inteiro(explicito: Optional[int], ambiente: str, padrao: int) -> int:
        if explicito is not None:
            return max(0, int(explicito))
        try:
            return max(0, int(os.getenv(ambiente, str(padrao))))
        except ValueError:
            return padrao

    def _dentro_da_validade(self, item: Dict[str, Any]) -> bool:
        idade = _idade_segundos(item.get("tempo_coleta"))
        if idade is None:
            return False
        return -300 <= idade <= self.validade_stale

    def _item_de_fonte_real(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        if item.get("fonte") not in FONTES_REAIS:
            return False
        preco = item.get("preco_atual")
        if isinstance(preco, bool) or not isinstance(preco, (int, float)):
            return False
        if not math.isfinite(float(preco)) or float(preco) <= 0:
            return False
        return self._dentro_da_validade(item)

    def _carregar_cache_real(self) -> None:
        if not self.caminho_snapshot.exists():
            return
        try:
            with open(self.caminho_snapshot, "r", encoding="utf-8") as arquivo:
                bruto = json.load(arquivo)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[Aviso] Snapshot de mercado ignorado: {exc}")
            return
        if not isinstance(bruto, dict):
            return
        for ticker in self.tickers:
            item = bruto.get(ticker)
            if not self._item_de_fonte_real(item):
                continue
            restaurado = dict(item)
            restaurado["disponivel"] = True
            restaurado["dados_stale"] = True
            restaurado["aviso"] = (
                "Última coleta real em disco. O preço não foi atualizado nesta execução."
            )
            self.resposta[ticker] = restaurado

    def _indisponivel(self, ticker: str, aviso: str) -> Dict[str, Any]:
        meta = METADADOS_ATIVOS.get(ticker, {"nome": ticker, "categoria": "B3"})
        return {
            "ticker": ticker,
            "preco_atual": None,
            "preco_fechamento_anterior": None,
            "variacao_dia_pct": None,
            "zscore_20p": None,
            "atr_14p": None,
            "volatilidade_20p": None,
            "tempo_referencia": None,
            "tempo_evento": None,
            "tempo_publicacao": None,
            "tempo_coleta": datetime.now(timezone.utc).isoformat(),
            "nome": meta["nome"],
            "categoria": meta["categoria"],
            "variacao_nominal": None,
            "sparkline": [],
            "fonte": None,
            "disponivel": False,
            "dados_stale": False,
            "aviso": aviso,
        }

    def _cache_fresco(self) -> bool:
        if self.ttl <= 0 or self._ultima_tentativa <= 0 or not self.resposta:
            return False
        return (time.monotonic() - self._ultima_tentativa) < self.ttl

    def _para_dict(self, metrica: Any) -> Dict[str, Any]:
        if hasattr(metrica, "__dataclass_fields__"):
            return asdict(metrica)
        return dict(metrica)

    def _aplicar_coleta(self, cesta: Dict[str, Any], erro_geral: Optional[str]) -> None:
        erros = getattr(self.coletor, "erros", {}) or {}
        antes = {ticker: dict(item) for ticker, item in self.resposta.items()}
        novos: Dict[str, Dict[str, Any]] = {}
        metricas: Dict[str, Any] = {}

        for ticker in self.tickers:
            metrica = cesta.get(ticker) if isinstance(cesta, dict) else None
            if metrica is not None:
                item = self._para_dict(metrica)
                if item.get("fonte") in FONTES_REAIS and self._preco_positivo(item.get("preco_atual")):
                    item["disponivel"] = True
                    item["dados_stale"] = False
                    item["aviso"] = None
                    novos[ticker] = item
                    metricas[ticker] = metrica
                    continue

            anterior = antes.get(ticker)
            if anterior and self._item_de_fonte_real(anterior):
                mantido = dict(anterior)
                mantido["disponivel"] = True
                mantido["dados_stale"] = True
                mantido["aviso"] = (
                    "Cotação desatualizada: a fonte real não respondeu. "
                    "O preço exibido é o da última coleta bem-sucedida."
                )
                novos[ticker] = mantido
                continue

            detalhe = erros.get(ticker) or erro_geral or "nenhuma fonte real respondeu com histórico suficiente"
            aviso = f"Cotação indisponível. {detalhe}"
            novos[ticker] = self._indisponivel(ticker, aviso[:280])

        self.resposta = novos
        self.dados_mercado = self.resposta
        self.metricas = metricas
        self._definir_evento(antes, novos)
        self._salvar_cache_real()
        resumo = ", ".join(
            (
                f"{ticker}={novos[ticker].get('preco_atual')}"
                f"[{novos[ticker].get('fonte') or 'indisponível'}"
                f"{'/stale' if novos[ticker].get('dados_stale') else ''}]"
            )
            for ticker in self.tickers
        )
        print(f"[Mercado] {resumo}")

    @staticmethod
    def _preco_positivo(preco: Any) -> bool:
        if isinstance(preco, bool) or not isinstance(preco, (int, float)):
            return False
        return math.isfinite(float(preco)) and float(preco) > 0

    def _definir_evento(self, antes: Dict[str, Dict[str, Any]], novos: Dict[str, Dict[str, Any]]) -> None:
        def assinatura(mapa: Dict[str, Dict[str, Any]]):
            return tuple(
                (
                    ticker,
                    bool((mapa.get(ticker) or {}).get("disponivel")),
                    bool((mapa.get(ticker) or {}).get("dados_stale")),
                )
                for ticker in self.tickers
            )

        if assinatura(antes) == assinatura(novos):
            return

        indisponiveis = [ticker for ticker in self.tickers if not novos[ticker].get("disponivel")]
        desatualizados = [ticker for ticker in self.tickers if novos[ticker].get("dados_stale")]
        if indisponiveis or desatualizados:
            partes = []
            if indisponiveis:
                partes.append("indisponível: " + ", ".join(indisponiveis))
            if desatualizados:
                partes.append("desatualizado: " + ", ".join(desatualizados))
            self.evento_pendente = {
                "tipo": "MERCADO",
                "tag": "FONTE",
                "cor": "amber",
                "titulo": "Coleta real incompleta",
                "mensagem": " ; ".join(partes) + ". Nenhum preço foi completado com simulação.",
            }
            return

        fontes = sorted({str(novos[ticker].get("fonte")) for ticker in self.tickers if novos[ticker].get("fonte")})
        referencias = ", ".join(
            f"{ticker} {novos[ticker].get('preco_atual')} @ {novos[ticker].get('tempo_referencia')}"
            for ticker in self.tickers
        )
        self.evento_pendente = {
            "tipo": "MERCADO",
            "tag": "COTAÇÃO REAL",
            "cor": "emerald",
            "titulo": "Cotações lidas da fonte de mercado",
            "mensagem": f"Fontes: {', '.join(fontes)}. {referencias}",
        }

    def _salvar_cache_real(self) -> None:
        existente: Dict[str, Any] = {}
        if self.caminho_snapshot.exists():
            try:
                with open(self.caminho_snapshot, "r", encoding="utf-8") as arquivo:
                    bruto = json.load(arquivo)
                if isinstance(bruto, dict):
                    existente = {
                        ticker: item
                        for ticker, item in bruto.items()
                        if isinstance(item, dict) and item.get("fonte") in FONTES_REAIS
                    }
            except (OSError, json.JSONDecodeError):
                existente = {}

        for ticker, item in self.resposta.items():
            if item.get("disponivel") and not item.get("dados_stale") and item.get("fonte") in FONTES_REAIS:
                existente[ticker] = item
        if not existente:
            return
        try:
            self.caminho_snapshot.parent.mkdir(parents=True, exist_ok=True)
            with open(self.caminho_snapshot, "w", encoding="utf-8") as arquivo:
                json.dump(existente, arquivo, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"[Aviso] Não foi possível gravar o cache de mercado: {exc}")

    def atualizar(self, forcar: bool = False) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if not forcar and self._cache_fresco():
                return json.loads(json.dumps(self.resposta))
            if self._em_coleta:
                if self.resposta:
                    return json.loads(json.dumps(self.resposta))
                return {
                    ticker: self._indisponivel(ticker, "Coleta em andamento.")
                    for ticker in self.tickers
                }
            self._em_coleta = True

        erro_geral = None
        try:
            cesta = self.coletor.coletar_cesta_completa() or {}
        except Exception as exc:  # noqa: BLE001 - a API precisa responder mesmo se a fonte cair
            cesta = {}
            erro_geral = f"{type(exc).__name__}: {exc}"

        with self._lock:
            try:
                self._aplicar_coleta(cesta, erro_geral)
                self._ultima_tentativa = time.monotonic()
                return json.loads(json.dumps(self.resposta))
            finally:
                self._em_coleta = False

    def obter_cotacoes(self) -> Dict[str, Dict[str, Any]]:
        return self.atualizar(forcar=False)

    def consumir_evento(self) -> Optional[Dict[str, str]]:
        with self._lock:
            evento = self.evento_pendente
            self.evento_pendente = None
            return evento
