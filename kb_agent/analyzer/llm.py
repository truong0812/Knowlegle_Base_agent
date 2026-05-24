from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI LLM client with file-based caching, batch processing, and error resilience."""

    def __init__(
        self,
        model: str = "gpt-4o",
        cache_dir: Path | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_concurrency: int = 2,
        chunk_size: int = 5,
        chunk_interval: float = 2.0,
    ) -> None:
        self._model = model
        self._cache_dir = cache_dir
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._chunk_size = chunk_size
        self._chunk_interval = chunk_interval
        self._json_mode_supported: dict[str, bool] = {}
        self._failure_log: Path | None = None

    def set_failure_log(self, path: Path) -> None:
        """Set path for logging LLM failures (.jsonl)."""
        self._failure_log = path
        path.parent.mkdir(parents=True, exist_ok=True)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        entry_id: str | None = None,
    ) -> dict:
        """Single LLM call with caching, JSON fallback, and retry on rate limit."""
        cache_key = self._cache_key(system_prompt, user_prompt)

        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        async with self._semaphore:
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    use_json_mode = self._json_mode_supported.get(self._model, True)
                    kwargs: dict = {
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    }
                    if use_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    response = await self._client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content or "{}"

                    result = json.loads(content)
                    self._save_cache(cache_key, result)
                    if not self._json_mode_supported.get(self._model):
                        self._json_mode_supported[self._model] = True
                    return result

                except json.JSONDecodeError:
                    if self._json_mode_supported.get(self._model, True):
                        self._json_mode_supported[self._model] = False
                        logger.info("JSON decode failed, retrying without json_object mode")
                        continue
                    parsed = self._parse_json_from_text(content)
                    if parsed:
                        self._save_cache(cache_key, parsed)
                        return parsed
                    self._log_failure(entry_id or cache_key[:12], "json_decode_error", content[:200])
                    return {}

                except Exception as e:
                    error_str = str(e)
                    is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
                    is_transient = any(
                        code in error_str for code in ("429", "503", "500", "timeout")
                    )

                    if is_rate_limit and attempt < max_attempts - 1:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            "Rate limited (attempt %d/%d), retrying in %.1fs",
                            attempt + 1, max_attempts, delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if is_transient and attempt < max_attempts - 1:
                        delay = (1.5 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            "Transient error (attempt %d/%d): %s",
                            attempt + 1, max_attempts, error_str[:100],
                        )
                        await asyncio.sleep(delay)
                        continue

                    error_type = "transient" if is_transient else "permanent"
                    self._log_failure(entry_id or cache_key[:12], error_type, error_str[:200])
                    raise

    async def batch_complete(
        self,
        prompts: list[tuple[str, str]],
        entry_ids: list[str] | None = None,
        progress_callback=None,
    ) -> list[dict]:
        """Process multiple prompts in chunks with bounded concurrency."""
        results: list[dict | None] = [None] * len(prompts)

        for chunk_start in range(0, len(prompts), self._chunk_size):
            chunk_end = min(chunk_start + self._chunk_size, len(prompts))
            chunk = prompts[chunk_start:chunk_end]

            chunk_results = await asyncio.gather(
                *(
                    self.complete(
                        sys_p,
                        user_p,
                        entry_id=entry_ids[i] if entry_ids else None,
                    )
                    for i, (sys_p, user_p) in enumerate(
                        zip(range(chunk_start, chunk_end), chunk, strict=False)
                    )
                ),
                return_exceptions=True,
            )

            for idx, r in enumerate(chunk_results):
                actual_idx = chunk_start + idx
                if isinstance(r, Exception):
                    logger.warning(
                        "LLM call failed for entry %s: %s",
                        entry_ids[actual_idx] if entry_ids else actual_idx,
                        r,
                    )
                    results[actual_idx] = {}
                else:
                    results[actual_idx] = r

            if progress_callback:
                progress_callback("batch", chunk_end, len(prompts))

            if chunk_end < len(prompts):
                await asyncio.sleep(self._chunk_interval)

        return [r if r is not None else {} for r in results]

    def _parse_json_from_text(self, text: str) -> dict | None:
        """Extract JSON from text that may contain markdown code blocks or raw text."""
        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding outermost braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _log_failure(self, entry_id: str, error_type: str, error_msg: str) -> None:
        """Log LLM failure to .kb/telemetry/llm_failures.jsonl."""
        if not self._failure_log:
            return
        record = {
            "timestamp": datetime.now().isoformat(),
            "entry_id": entry_id,
            "model": self._model,
            "error_type": error_type,
            "error": error_msg,
        }
        try:
            with open(self._failure_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.debug("Failed to write LLM failure log")

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
