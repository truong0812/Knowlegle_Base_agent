from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openai import OpenAI


class LLMClient:
    """OpenAI LLM client with file-based caching and batch processing."""

    def __init__(
        self,
        model: str = "gpt-4o",
        cache_dir: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._cache_dir = cache_dir
        self._client = OpenAI(api_key=api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> dict:
        """Single LLM call with caching. Returns parsed JSON dict."""
        cache_key = self._cache_key(system_prompt, user_prompt)

        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        self._save_cache(cache_key, result)
        return result

    async def batch_complete(
        self, prompts: list[tuple[str, str]]
    ) -> list[dict]:
        """Process multiple prompts sequentially (with caching)."""
        return [await self.complete(sys_p, user_p) for sys_p, user_p in prompts]

    def _cache_key(self, system_prompt: str, user_prompt: str) -> str:
        return hashlib.sha256(
            f"{system_prompt}||{user_prompt}".encode()
        ).hexdigest()

    def _load_cache(self, key: str) -> dict | None:
        if not self._cache_dir:
            return None
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None

    def _save_cache(self, key: str, response: dict) -> None:
        if not self._cache_dir:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
