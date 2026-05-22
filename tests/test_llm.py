"""Tests for LLM client — async, caching, batch."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kb_agent.analyzer.llm import LLMClient


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


def _make_client(**kwargs):
    with patch("kb_agent.analyzer.llm.AsyncOpenAI"):
        return LLMClient(**kwargs)


class TestLLMClient:
    def test_uses_async_client(self):
        with patch("kb_agent.analyzer.llm.AsyncOpenAI") as mock_cls:
            LLMClient(model="gpt-4o", api_key="test-key")
            mock_cls.assert_called_once_with(api_key="test-key", base_url=None)

    def test_uses_custom_base_url(self):
        with patch("kb_agent.analyzer.llm.AsyncOpenAI") as mock_cls:
            LLMClient(model="gpt-4o", api_key="test-key", base_url="http://localhost:11434/v1")
            mock_cls.assert_called_once_with(api_key="test-key", base_url="http://localhost:11434/v1")

    def test_cache_hit(self, cache_dir: Path):
        client = _make_client(cache_dir=cache_dir)
        # Pre-seed cache
        cache_key = client._cache_key("sys", "user")
        cached = {"summary": "cached result", "confidence": 0.8}
        (cache_dir / f"{cache_key}.json").write_text(json.dumps(cached))

        result = asyncio.run(client.complete("sys", "user"))
        assert result == cached

    def test_cache_miss_calls_api(self, cache_dir: Path):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content='{"summary": "test", "confidence": 0.9}'))
        ]

        client = _make_client(cache_dir=cache_dir)
        mock_create = AsyncMock(return_value=fake_response)
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        client._client = mock_client

        result = asyncio.run(client.complete("system prompt", "user prompt"))
        assert result["summary"] == "test"
        assert result["confidence"] == 0.9

    def test_batch_complete(self, cache_dir: Path):
        call_count = 0

        async def fake_complete(sys_p, user_p):
            nonlocal call_count
            call_count += 1
            return {"summary": f"result-{call_count}"}

        client = _make_client(cache_dir=cache_dir)
        client.complete = fake_complete

        prompts = [("sys1", "usr1"), ("sys2", "usr2"), ("sys3", "usr3")]
        results = asyncio.run(client.batch_complete(prompts))

        assert len(results) == 3
        assert call_count == 3

    def test_cache_file_written(self, cache_dir: Path):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content='{"summary": "new", "confidence": 0.7}'))
        ]

        client = _make_client(cache_dir=cache_dir)
        mock_create = AsyncMock(return_value=fake_response)
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        client._client = mock_client

        asyncio.run(client.complete("sys", "usr"))

        cache_files = list(cache_dir.glob("*.json"))
        assert len(cache_files) == 1
        data = json.loads(cache_files[0].read_text())
        assert data["summary"] == "new"
