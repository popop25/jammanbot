from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = (model or os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        data = self._generate(prompt)
        return _extract_text(data)

    def generate_json(self, prompt: str) -> dict[str, Any]:
        text = self.generate_text(prompt)
        return _parse_json_object(text)

    def _generate(self, prompt: str) -> dict[str, Any]:
        url = GEMINI_ENDPOINT.format(model=self.model)
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
            },
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, params={"key": self.api_key}, json=payload)
            response.raise_for_status()
            return response.json()


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [str(part.get("text") or "") for part in parts if part.get("text")]
        if texts:
            return "\n".join(texts).strip()
    return ""


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        stripped = stripped[start : end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response is not a JSON object.")
    return parsed
