"""
Cliente Unificado de Modelos de Linguagem (LLM Client).
Suporta chamadas estruturadas e tipadas para:
- Google Gemini (Gemini 1.5 Flash / 2.0)
- Anthropic Claude (Claude 3.5 Sonnet / Haiku)
- OpenAI (GPT-4o / GPT-4o-mini)
- Groq / OpenRouter / DeepSeek (OpenAI-compatible)

Garante que as respostas sejam extraídas em JSON válido, com fallback gracioso.
"""

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Dict, Optional, Tuple
import requests


@dataclass
class InfoProvedor:
    ativo: bool
    provedor: str
    modelo: str
    detalhes: str


class LLMClient:
    def __init__(self):
        self.provedor_ativo, self.chave_api, self.modelo_padrao = self._detectar_provedor()

    def _detectar_provedor(self) -> Tuple[str, Optional[str], str]:
        # 1. Google Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            modelo = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            return "gemini", gemini_key, modelo

        # 2. Anthropic Claude
        claude_key = os.environ.get("ANTHROPIC_API_KEY")
        if claude_key:
            modelo = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
            return "anthropic", claude_key, modelo

        # 3. OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            modelo = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            return "openai", openai_key, modelo

        # 4. xAI Grok
        grok_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
        if grok_key:
            modelo = os.environ.get("GROK_MODEL", "grok-2-latest")
            return "grok", grok_key, modelo

        # 5. Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            modelo = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            return "groq", groq_key, modelo

        return "nenhum", None, "simulador_deterministico"

    def obter_status(self) -> InfoProvedor:
        if self.provedor_ativo != "nenhum":
            return InfoProvedor(
                ativo=True,
                provedor=self.provedor_ativo.upper(),
                modelo=self.modelo_padrao,
                detalhes=f"Conectado ao cérebro {self.provedor_ativo.upper()} ({self.modelo_padrao}).",
            )
        return InfoProvedor(
            ativo=False,
            provedor="SIMULADOR_LOCAL",
            modelo="regras_deterministicas",
            detalhes="Nenhuma chave detectada (GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY). Operando no modo contingência.",
        )

    def reconfigurar_chave(self, provedor: str, chave: str, modelo: Optional[str] = None) -> None:
        if provedor.lower() == "gemini":
            os.environ["GEMINI_API_KEY"] = chave
        elif provedor.lower() == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = chave
        elif provedor.lower() == "openai":
            os.environ["OPENAI_API_KEY"] = chave
        elif provedor.lower() in ("grok", "xai"):
            os.environ["GROK_API_KEY"] = chave
            os.environ["XAI_API_KEY"] = chave
            if modelo:
                os.environ["GROK_MODEL"] = modelo
        elif provedor.lower() == "groq":
            os.environ["GROQ_API_KEY"] = chave
        self.provedor_ativo, self.chave_api, self.modelo_padrao = self._detectar_provedor()

    def gerar_json(self, prompt_sistema: str, prompt_usuario: str) -> Optional[Dict[str, Any]]:
        """
        Executa a inferência no provedor ativo e garante retorno de dicionário JSON.
        """
        if self.provedor_ativo == "nenhum" or not self.chave_api:
            return None

        try:
            if self.provedor_ativo == "gemini":
                return self._chamar_gemini(prompt_sistema, prompt_usuario)
            elif self.provedor_ativo == "anthropic":
                return self._chamar_anthropic(prompt_sistema, prompt_usuario)
            elif self.provedor_ativo in ("openai", "groq", "grok"):
                return self._chamar_openai_compativel(prompt_sistema, prompt_usuario)
        except Exception as e:
            print(f"[Aviso LLM] Falha na chamada da API ({self.provedor_ativo}): {e}")
            return None

    def _chamar_gemini(self, sistema: str, usuario: str) -> Optional[Dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo_padrao}:generateContent?key={self.chave_api}"
        payload = {
            "system_instruction": {"parts": [{"text": sistema}]},
            "contents": [{"parts": [{"text": usuario}]}],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }
        res = requests.post(url, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        texto = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(texto)

    def _chamar_anthropic(self, sistema: str, usuario: str) -> Optional[Dict[str, Any]]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.chave_api,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.modelo_padrao,
            "max_tokens": 2048,
            "system": sistema,
            "messages": [{"role": "user", "content": usuario}],
            "temperature": 0.1,
        }
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        texto = data["content"][0]["text"]
        return self._extrair_json_de_texto(texto)

    def _chamar_openai_compativel(self, sistema: str, usuario: str) -> Optional[Dict[str, Any]]:
        if self.provedor_ativo == "grok":
            base_url = "https://api.x.ai/v1"
        elif self.provedor_ativo == "groq":
            base_url = "https://api.groq.com/openai/v1"
        else:
            base_url = "https://api.openai.com/v1"

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.chave_api}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.modelo_padrao,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        texto = data["choices"][0]["message"]["content"]
        return json.loads(texto)

    def _extrair_json_de_texto(self, texto: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(texto)
