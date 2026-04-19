from __future__ import annotations

import json
from typing import Any

import httpx


class LLMChatClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def complete_json(self, *, model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        body = self._request_chat_completion(payload)
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)

    def complete_text(self, *, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        body = self._request_chat_completion(payload)
        content = body["choices"][0]["message"].get("content") or ""
        return str(content).strip()

    def _request_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            if payload.get("response_format") and response.status_code == 400:
                retry_payload = {key: value for key, value in payload.items() if key != "response_format"}
                retry_response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=retry_payload,
                    timeout=self.timeout_seconds,
                )
                retry_response.raise_for_status()
                return retry_response.json()
            raise
        return response.json()