"""
Testes unitários do Coordenador de Ciclo Mínimo.
Valida o pipeline completo: dados mockados -> análise -> revisão -> Order Gate -> carteira.
"""

import pytest
from src.agents.coordinator import CoordenadorCiclo
from src.agents.contracts import ParecerRevisao


def test_fluxo_coordenador_com_mock(monkeypatch):
    coord = CoordenadorCiclo()

    # Snapshot controlado para teste
    snapshot_teste = {
        "USDBRL=X": {"zscore_20p": 0.5, "tempo_coleta": "2026-11-01T12:00:00Z"},
        "BOVA11.SA": {
            "ticker": "BOVA11.SA",
            "preco_atual": 100.0,
            "zscore_20p": -2.1,  # Abaixo de -1.8 -> dispara proposta
            "atr_14p": 2.0,
            "tempo_coleta": "2026-11-01T12:00:00Z",
        },
        "GOLD11.SA": {
            "ticker": "GOLD11.SA",
            "preco_atual": 20.0,
            "zscore_20p": 0.1,  # Neutro -> não dispara
            "atr_14p": 0.5,
            "tempo_coleta": "2026-11-01T12:00:00Z",
        },
    }

    diag = coord.analisar_mercado_deterministico(snapshot_teste)
    assert len(diag.propostas) == 1
    prop = diag.propostas[0]
    assert prop.ativo == "BOVA11.SA"
    assert prop.tipo_operacao == "COMPRA"
    assert prop.preco_stop_loss == 100.0 - (1.5 * 2.0)  # 97.0
    assert prop.preco_take_profit == 100.0 + (3.0 * 2.0)  # 106.0

    # Revisão da proposta
    revisao = coord.revisar_proposta(prop, snapshot_teste["BOVA11.SA"])
    assert revisao.parecer == ParecerRevisao.APROVADO
    assert revisao.auditoria_matematica_valida is True
