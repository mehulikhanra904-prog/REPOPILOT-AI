"""Provider-neutral LLM integration with a useful no-key fallback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import Settings


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    async def complete(self, system: str, prompt: str) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system: str, prompt: str) -> str:
        url = self.settings.openai_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        payload = {
            "model": self.settings.openai_model,
            "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"LLM provider returned HTTP {response.status_code}.")
        data = response.json()
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system: str, prompt: str) -> str:
        payload = {
            "model": self.settings.anthropic_model,
            "max_tokens": 1200,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"LLM provider returned HTTP {response.status_code}.")
        data = response.json()
        return "\n".join(block.get("text", "") for block in data.get("content", [])).strip()


def build_provider(settings: Settings) -> LLMProvider | None:
    if settings.llm_provider in {"openai", "openai-compatible"} and settings.openai_api_key:
        return OpenAICompatibleProvider(settings)
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings)
    return None


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = build_provider(settings)

    @property
    def powered_by(self) -> str:
        return self.provider.name if self.provider else "local-analysis"

    async def answer(self, system: str, prompt: str, fallback: str) -> tuple[str, str]:
        if self.provider:
            try:
                return await self.provider.complete(system, prompt), self.provider.name
            except (httpx.HTTPError, RuntimeError, KeyError, IndexError, TypeError):
                return fallback, "local-analysis (provider unavailable)"
        return fallback, "local-analysis"


def fallback_question(analysis: dict[str, Any], question: str) -> str:
    repository = analysis["repository"]
    languages = ", ".join(language["name"] for language in analysis.get("languages", [])[:4]) or "not detected"
    issues = analysis.get("quality", {}).get("issues", [])
    lowered = question.lower()
    if "bug" in lowered or "issue" in lowered or "quality" in lowered:
        if issues:
            bullets = "\n".join(
                f"- **{issue['title']}**"
                f"{(' in `' + issue['file'] + '`') if issue.get('file') else ''}: "
                f"{issue['description']}"
                for issue in issues[:5]
            )
            return f"I’m running without an external LLM key, so this is based on RepoPilot’s static scan.\n\n{bullets}"
        return "The static scan did not find high-confidence issues in the sampled source files. Add an LLM key for a deeper review."
    if "language" in lowered or "stack" in lowered:
        return f"This repository is primarily composed of {languages}. It contains {analysis.get('file_count', 0)} files across {analysis.get('directory_count', 0)} directories and uses `{repository.get('default_branch')}` as its default branch."
    return f"I can inspect **{repository.get('full_name')}** using its metadata, file tree, and static quality signals. This local fallback is active because no LLM credentials are configured. Ask about the stack, potential bugs, or a specific file for a focused answer."
