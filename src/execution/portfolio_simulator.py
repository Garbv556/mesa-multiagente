"""
Simulador de Carteira e Gestão de Posições (Paper Trading).
Mantém o registro consistente de saldo, posições, movimentações e histórico.
Idempotente e auditável.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
import uuid


class EstadoOrdem(str, Enum):
    PREPARADA = "PREPARADA"
    VALIDADA = "VALIDADA"
    EXECUTADA = "EXECUTADA"
    REJEITADA = "REJEITADA"
    CANCELADA = "CANCELADA"


class TipoOperacao(str, Enum):
    COMPRA = "COMPRA"
    VENDA = "VENDA"


@dataclass
class Ordem:
    ordem_id: str
    ativo: str
    tipo: TipoOperacao
    quantidade: float
    preco_execucao: float
    preco_stop_loss: float
    preco_take_profit: float
    taxa_corretagem: float
    estado: EstadoOrdem
    timestamp: str
    justificativa: str = ""


@dataclass
class Posicao:
    ativo: str
    quantidade: float
    preco_medio: float
    preco_atual: float

    @property
    def valor_mercado(self) -> float:
        return self.quantidade * self.preco_atual

    @property
    def pl_nao_realizado(self) -> float:
        return self.quantidade * (self.preco_atual - self.preco_medio)


class CarteiraSimulada:
    def __init__(self, saldo_inicial_brl: float = 100.0):
        self.saldo_caixa: float = float(saldo_inicial_brl)
        self.capital_inicial: float = float(saldo_inicial_brl)
        self.posicoes: Dict[str, Posicao] = {}
        self.historico_ordens: List[Ordem] = []
        self.perdas_consecutivas_hoje: int = 0
        self.pl_realizado_hoje: float = 0.0

    @property
    def patrimonio_total(self) -> float:
        valor_posicoes = sum(p.valor_mercado for p in self.posicoes.values())
        return self.saldo_caixa + valor_posicoes

    def atualizar_cotacao(self, ativo: str, preco: float) -> None:
        if ativo in self.posicoes:
            self.posicoes[ativo].preco_atual = preco

    def executar_compra(
        self,
        ativo: str,
        quantidade: float,
        preco: float,
        preco_stop_loss: float,
        preco_take_profit: float,
        taxa_corretagem: float = 0.0,
        justificativa: str = "",
    ) -> Ordem:
        custo_total = (quantidade * preco) + taxa_corretagem
        if custo_total > self.saldo_caixa:
            ordem_recusada = Ordem(
                ordem_id=str(uuid.uuid4())[:8],
                ativo=ativo,
                tipo=TipoOperacao.COMPRA,
                quantidade=quantidade,
                preco_execucao=preco,
                preco_stop_loss=preco_stop_loss,
                preco_take_profit=preco_take_profit,
                taxa_corretagem=taxa_corretagem,
                estado=EstadoOrdem.REJEITADA,
                timestamp=datetime.now(timezone.utc).isoformat(),
                justificativa="Saldo em caixa insuficiente.",
            )
            self.historico_ordens.append(ordem_recusada)
            return ordem_recusada

        self.saldo_caixa -= custo_total

        if ativo in self.posicoes:
            pos = self.posicoes[ativo]
            qtd_antiga = pos.quantidade
            novo_custo = (qtd_antiga * pos.preco_medio) + (quantidade * preco)
            pos.quantidade += quantidade
            pos.preco_medio = novo_custo / pos.quantidade
            pos.preco_atual = preco
        else:
            self.posicoes[ativo] = Posicao(
                ativo=ativo,
                quantidade=quantidade,
                preco_medio=preco,
                preco_atual=preco,
            )

        ordem_sucesso = Ordem(
            ordem_id=str(uuid.uuid4())[:8],
            ativo=ativo,
            tipo=TipoOperacao.COMPRA,
            quantidade=quantidade,
            preco_execucao=preco,
            preco_stop_loss=preco_stop_loss,
            preco_take_profit=preco_take_profit,
            taxa_corretagem=taxa_corretagem,
            estado=EstadoOrdem.EXECUTADA,
            timestamp=datetime.now(timezone.utc).isoformat(),
            justificativa=justificativa,
        )
        self.historico_ordens.append(ordem_sucesso)
        return ordem_sucesso

    def executar_venda(
        self,
        ativo: str,
        quantidade: float,
        preco: float,
        taxa_corretagem: float = 0.0,
        justificativa: str = "",
    ) -> Ordem:
        if ativo not in self.posicoes or self.posicoes[ativo].quantidade < quantidade:
            ordem_recusada = Ordem(
                ordem_id=str(uuid.uuid4())[:8],
                ativo=ativo,
                tipo=TipoOperacao.VENDA,
                quantidade=quantidade,
                preco_execucao=preco,
                preco_stop_loss=0.0,
                preco_take_profit=0.0,
                taxa_corretagem=taxa_corretagem,
                estado=EstadoOrdem.REJEITADA,
                timestamp=datetime.now(timezone.utc).isoformat(),
                justificativa="Posição insuficiente para venda.",
            )
            self.historico_ordens.append(ordem_recusada)
            return ordem_recusada

        pos = self.posicoes[ativo]
        receita_liquida = (quantidade * preco) - taxa_corretagem
        pl_operacao = (preco - pos.preco_medio) * quantidade - taxa_corretagem

        self.saldo_caixa += receita_liquida
        self.pl_realizado_hoje += pl_operacao

        if pl_operacao < 0:
            self.perdas_consecutivas_hoje += 1
        else:
            self.perdas_consecutivas_hoje = 0

        pos.quantidade -= quantidade
        if pos.quantidade <= 0.000001:
            del self.posicoes[ativo]
        else:
            pos.preco_atual = preco

        ordem_sucesso = Ordem(
            ordem_id=str(uuid.uuid4())[:8],
            ativo=ativo,
            tipo=TipoOperacao.VENDA,
            quantidade=quantidade,
            preco_execucao=preco,
            preco_stop_loss=0.0,
            preco_take_profit=0.0,
            taxa_corretagem=taxa_corretagem,
            estado=EstadoOrdem.EXECUTADA,
            timestamp=datetime.now(timezone.utc).isoformat(),
            justificativa=justificativa,
        )
        self.historico_ordens.append(ordem_sucesso)
        return ordem_sucesso
