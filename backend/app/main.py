"""FastAPI entry point for RepoPilot AI."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .github import GitHubAPIError, GitHubRepositoryAnalyzer, parse_repo_url
from .llm import LLMService, fallback_question
from .models import AskRequest, ExplainRequest, FileRequest, RepositoryRequest


app = FastAPI(
    title="RepoPilot AI API",
    version="1.0.0",
    description="Repository intelligence API with GitHub analysis and modular LLM support.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = GitHubRepositoryAnalyzer(settings)
llm_service = LLMService(settings)
analysis_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(repo_url: str) -> str:
    owner, repo = parse_repo_url(repo_url)
    return f"{owner.lower()}/{repo.lower()}"


async def _get_analysis(repo_url: str, force_refresh: bool = False) -> dict[str, Any]:
    key = _cache_key(repo_url)
    cached = analysis_cache.get(key)
    if cached and not force_refresh and monotonic() - cached[0] < settings.analysis_cache_ttl_seconds:
        return cached[1]
    result = await analyzer.analyze(repo_url)
    if len(analysis_cache) >= settings.analysis_cache_max_entries:
        oldest_key = min(analysis_cache, key=lambda cache_key: analysis_cache[cache_key][0])
        analysis_cache.pop(oldest_key, None)
    analysis_cache[key] = (monotonic(), result)
    return result


def _handle_error(error: Exception) -> HTTPException:
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, GitHubAPIError):
        return HTTPException(status_code=error.status_code, detail=error.detail)
    return HTTPException(status_code=502, detail="GitHub could not be reached. Please try again.")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "ai_provider": llm_service.powered_by}


@app.post("/api/analyze")
async def analyze_repository(request: RepositoryRequest) -> dict[str, Any]:
    try:
        return await _get_analysis(request.repo_url, request.force_refresh)
    except Exception as error:
        raise _handle_error(error) from error


@app.post("/api/file")
async def get_file(request: FileRequest) -> dict[str, Any]:
    try:
        return await analyzer.fetch_file(request.repo_url, request.path)
    except Exception as error:
        raise _handle_error(error) from error


@app.post("/api/ask")
async def ask_repository(request: AskRequest) -> dict[str, str]:
    try:
        analysis = await _get_analysis(request.repo_url, request.force_refresh)
        selected_context = ""
        if request.selected_path:
            try:
                selected = await analyzer.fetch_file(request.repo_url, request.selected_path)
                selected_context = f"\nSelected file ({selected['path']}):\n{selected['content'][:14000]}"
            except Exception:
                selected_context = "\nThe selected file could not be fetched."
        context = _analysis_context(analysis) + selected_context
        fallback = fallback_question(analysis, request.question)
        answer, powered_by = await llm_service.answer(
            "You are RepoPilot AI, a concise senior engineer. Use only the supplied repository context. Mention uncertainty and give actionable steps.",
            f"Repository context:\n{context}\n\nQuestion: {request.question}",
            fallback,
        )
        return {"answer": answer, "powered_by": powered_by}
    except Exception as error:
        raise _handle_error(error) from error


@app.post("/api/explain")
async def explain_file(request: ExplainRequest) -> dict[str, str]:
    try:
        analysis = await _get_analysis(request.repo_url, request.force_refresh)
        file = await analyzer.fetch_file(request.repo_url, request.path)
        prompt = request.question or "Explain this file's purpose, key control flow, dependencies, and one improvement opportunity."
        fallback = (
            f"**{file['path']}** is detected as {file.get('language') or 'a text file'} and contains "
            f"{len(file['content'].splitlines())} lines.\n\n"
            "No external LLM key is configured, so RepoPilot can show the source and static repository context, "
            "but a provider key is required for a generated line-by-line explanation."
        )
        answer, powered_by = await llm_service.answer(
            "You explain source code for developers. Be concrete, cite symbols or line ranges when visible, and do not invent behavior.",
            f"Repository: {_analysis_context(analysis)}\n\nFile: {file['path']}\n```\n{file['content'][:18000]}\n```\n\nRequest: {prompt}",
            fallback,
        )
        return {"answer": answer, "powered_by": powered_by}
    except Exception as error:
        raise _handle_error(error) from error


def _analysis_context(analysis: dict[str, Any]) -> str:
    repo = analysis["repository"]
    languages = ", ".join(f"{item['name']} ({item['percentage']}%)" for item in analysis.get("languages", [])[:6])
    tree = ", ".join(item["path"] for item in analysis.get("tree", [])[:120])
    issues = "; ".join(issue["title"] for issue in analysis.get("quality", {}).get("issues", [])[:8]) or "none found"
    return (
        f"{repo.get('full_name')} — {repo.get('description')}\n"
        f"Default branch: {repo.get('default_branch')}; Languages: {languages or 'not detected'}; "
        f"Files: {analysis.get('file_count', 0)}; Quality score: {analysis.get('quality', {}).get('score', 0)}/100; "
        f"Potential signals: {issues}\nTree sample: {tree}"
    )


# The production Docker image copies the Vite build here. In local development,
# Vite owns the frontend and this directory simply does not exist.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
