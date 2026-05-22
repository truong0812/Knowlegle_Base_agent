from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from openai import AsyncOpenAI


class LLMClient:
    """OpenAI LLM client with file-based caching and batch processing."""

    def __init__(
        self,
        model: str = "gpt-4o",
        cache_dir: Path | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self._model = model
        self._cache_dir = cache_dir
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def complete(self, system_prompt: str, user_prompt: str) -> dict:
        """Single LLM call with caching and retry on rate limit."""
        cache_key = self._cache_key(system_prompt, user_prompt)

        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        async with self._semaphore:
            for attempt in range(3):
                try:
                    response = await self._client.chat.completions.create(
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
                except Exception as e:
                    is_rate_limit = "429" in str(e)
                    if is_rate_limit and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise

    async def batch_complete(
        self, prompts: list[tuple[str, str]]
    ) -> list[dict]:
        """Process multiple prompts with bounded concurrency."""
        return await asyncio.gather(
            *(self.complete(sys_p, user_p) for sys_p, user_p in prompts)
        )

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
