"""
Testes unitários do cliente LLM e dos endpoints de configuração de IA.
"""

from unittest.mock import patch
import pytest
from src.agents.llm_client import LLMClient
from fastapi.testclient import TestClient
from src.dashboard.app import app

client = TestClient(app)


def test_llm_client_status_sem_chave(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    llm = LLMClient()
    status = llm.obter_status()
    assert status.ativo is False
    assert status.provedor == "SIMULADOR_LOCAL"


def test_llm_client_deteccao_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "teste_chave_gemini_12345")
    llm = LLMClient()
    status = llm.obter_status()
    assert status.ativo is True
    assert status.provedor == "GEMINI"
    assert "gemini" in status.modelo


def test_api_configurar_llm():
    resp = client.post(
        "/api/llm/configure",
        json={"provedor": "gemini", "chave": "AIzaSyFakeKeyForTesting123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provedor"] == "GEMINI"

    # Confere se o status agora reflete a chave
    status_resp = client.get("/api/llm/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["ativo"] is True
