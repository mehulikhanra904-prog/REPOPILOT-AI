"""Small, defensive GitHub API client and repository analyzer."""

from __future__ import annotations

import asyncio
import base64
from collections import Counter
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .config import Settings


LANGUAGE_COLORS = {
    "Python": "#f2c94c",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Go": "#00add8",
    "Rust": "#dea584",
    "Java": "#b07219",
    "C#": "#178600",
    "C++": "#f34b7d",
    "Ruby": "#701516",
    "PHP": "#4f5d95",
    "Shell": "#89e051",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
}

SOURCE_EXTENSIONS = set(LANGUAGE_BY_EXTENSION) - {".json", ".yaml", ".yml", ".md"}


class GitHubAPIError(Exception):
    """An API error that can be shown as a useful user-facing message."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def parse_repo_url(value: str) -> tuple[str, str]:
    """Return owner and repo from a GitHub URL or owner/repo shorthand."""

    value = value.strip()
    if not value:
        raise ValueError("Enter a GitHub repository URL.")

    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Only github.com repository URLs are supported.")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("Use a repository URL such as https://github.com/owner/repository.")

    owner, repo = parts[0], re.sub(r"\.git$", "", parts[1])
    if not owner or not repo or any(char in owner + repo for char in "?#"):
        raise ValueError("That GitHub repository URL is not valid.")
    return owner, repo


def language_for_path(path: str) -> str | None:
    path_lower = path.lower()
    for extension, language in LANGUAGE_BY_EXTENSION.items():
        if path_lower.endswith(extension):
            return language
    return None


def is_source_path(path: str) -> bool:
    return any(path.lower().endswith(extension) for extension in SOURCE_EXTENSIONS)


def _quality_issue(severity: str, title: str, description: str, file_path: str | None = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "title": title,
        "description": description,
        "file": file_path,
    }


def architecture_for_tree(tree: list[dict[str, Any]], language_names: list[str]) -> dict[str, Any]:
    """Infer useful architecture signals without requiring an LLM."""

    file_paths = [item["path"] for item in tree if item["type"] == "file"]
    lowered = {path.lower() for path in file_paths}
    stacks: list[str] = []
    if {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"} & lowered:
        stacks.append("Node.js")
    if {"pyproject.toml", "requirements.txt", "requirements.lock", "setup.py", "pipfile"} & lowered:
        stacks.append("Python")
    if "cargo.toml" in lowered:
        stacks.append("Rust")
    if "go.mod" in lowered:
        stacks.append("Go")
    if "pom.xml" in lowered or "build.gradle" in lowered:
        stacks.append("JVM")
    if any(path.endswith((".csproj", ".sln")) for path in lowered):
        stacks.append(".NET")
    for language in language_names:
        if language not in stacks and language in {"JavaScript", "TypeScript", "Python", "Go", "Rust", "Java", "C#"}:
            stacks.append(language)

    entrypoint_names = {"main.py", "app.py", "server.py", "manage.py", "index.js", "index.ts", "main.go", "main.rs", "package.json"}
    entrypoints = [
        path for path in file_paths
        if path.lower().split("/")[-1] in entrypoint_names
    ][:12]
    test_files = [
        path for path in file_paths
        if any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in path.lower().split("/"))
        or ".test." in path.lower()
        or ".spec." in path.lower()
    ]
    workflow_count = sum(path.lower().startswith(".github/workflows/") for path in file_paths)
    documentation_count = sum(
        path.lower().endswith((".md", ".rst", ".adoc")) or path.lower().startswith("docs/")
        for path in file_paths
    )
    layer_names = {
        part.split("/", 1)[0].lower()
        for part in file_paths
        if "/" in part
    }
    layers = [
        layer for layer in ("src", "app", "api", "backend", "frontend", "components", "services", "lib", "tests", "docs", "scripts")
        if layer in layer_names
    ]
    stack_label = " + ".join(stacks[:3]) or "Mixed-language"
    layout_label = ", ".join(f"`{layer}/`" for layer in layers[:4]) or "a flat root layout"
    summary = f"{stack_label} repository organized around {layout_label}."
    if test_files:
        summary += f" {len(test_files)} test-related files were detected."
    elif workflow_count:
        summary += " CI workflows are present, but no obvious test paths were found."
    else:
        summary += " Add or review automated tests before making broad changes."
    return {
        "stacks": stacks[:8],
        "entrypoints": entrypoints,
        "test_file_count": len(test_files),
        "workflow_count": workflow_count,
        "documentation_file_count": documentation_count,
        "layers": layers,
        "summary": summary,
    }


@dataclass
class GitHubRepositoryAnalyzer:
    settings: Settings

    async def _request(self, client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await client.get(path, params=params)
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            if response.status_code == 403:
                message = "GitHub rate limit reached. Add a GITHUB_TOKEN in .env and try again."
            elif response.status_code == 404:
                message = "Repository not found, or it is private without a valid GITHUB_TOKEN."
            raise GitHubAPIError(response.status_code, str(message))
        return response.json()

    async def _safe_request(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any] | None = None,
        fallback: Any = None,
    ) -> Any:
        try:
            return await self._request(client, path, params)
        except GitHubAPIError:
            return fallback if fallback is not None else []

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoPilot-AI/1.0",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=self.settings.api_timeout_seconds,
            follow_redirects=True,
        )

    async def _file_from_client(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> dict[str, Any]:
        payload = await self._request(
            client,
            f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path, safe='/')}",
            {"ref": branch},
        )
        if isinstance(payload, list) or payload.get("type") != "file":
            raise GitHubAPIError(422, "The selected path is not a file.")
        encoded = payload.get("content", "").replace("\n", "")
        try:
            content = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except (ValueError, base64.binascii.Error):
            content = "This file is binary or could not be decoded as UTF-8."
        return {
            "path": path,
            "name": path.rsplit("/", 1)[-1],
            "language": language_for_path(path),
            "size": payload.get("size", len(content.encode("utf-8"))),
            "content": content,
            "html_url": payload.get("html_url"),
        }

    async def fetch_file(self, repo_url: str, path: str) -> dict[str, Any]:
        owner, repo = parse_repo_url(repo_url)
        async with self._client() as client:
            metadata = await self._request(client, f"/repos/{quote(owner)}/{quote(repo)}")
            return await self._file_from_client(client, owner, repo, path.strip("/"), metadata["default_branch"])

    async def analyze(self, repo_url: str) -> dict[str, Any]:
        owner, repo = parse_repo_url(repo_url)
        async with self._client() as client:
            metadata, language_bytes = await asyncio.gather(
                self._request(client, f"/repos/{quote(owner)}/{quote(repo)}"),
                self._request(client, f"/repos/{quote(owner)}/{quote(repo)}/languages"),
            )
            branch = metadata.get("default_branch") or "main"
            tree_payload = await self._request(
                client,
                f"/repos/{quote(owner)}/{quote(repo)}/git/trees/{quote(branch, safe='')}",
                {"recursive": "1"},
            )
            commits_payload = await self._safe_request(
                client,
                f"/repos/{quote(owner)}/{quote(repo)}/commits",
                {"per_page": "6"},
            )
            raw_tree = tree_payload.get("tree", [])
            tree = [
                {
                    "path": item.get("path", ""),
                    "type": "file" if item.get("type") == "blob" else "directory",
                    "size": item.get("size", 0),
                    "language": language_for_path(item.get("path", "")),
                }
                for item in raw_tree
                if item.get("path")
            ]
            tree.sort(key=lambda item: (item["type"] != "directory", item["path"].lower()))

            source_files = [
                item for item in tree if item["type"] == "file" and is_source_path(item["path"])
            ]
            preview_candidates = sorted(source_files, key=lambda item: (item["path"].count("/"), -item["size"]))[:10]
            preview_results = await asyncio.gather(
                *(self._file_from_client(client, owner, repo, item["path"], branch) for item in preview_candidates),
                return_exceptions=True,
            )

        previews = [item for item in preview_results if isinstance(item, dict)]
        issues = self._find_quality_issues(previews, tree)
        languages = self._format_languages(language_bytes)
        architecture = architecture_for_tree(tree, [item["name"] for item in languages])
        score = max(46, 100 - sum(16 if issue["severity"] == "high" else 9 if issue["severity"] == "medium" else 4 for issue in issues))
        grade = "A" if score >= 90 else "B" if score >= 78 else "C" if score >= 64 else "D"
        directories = [item for item in tree if item["type"] == "directory"]
        files = [item for item in tree if item["type"] == "file"]

        return {
            "repository": {
                "name": metadata.get("name"),
                "full_name": metadata.get("full_name"),
                "owner": metadata.get("owner", {}).get("login", owner),
                "description": metadata.get("description") or "No repository description provided.",
                "html_url": metadata.get("html_url"),
                "default_branch": branch,
                "stars": metadata.get("stargazers_count", 0),
                "forks": metadata.get("forks_count", 0),
                "open_issues": metadata.get("open_issues_count", 0),
                "watchers": metadata.get("watchers_count", 0),
                "license": (metadata.get("license") or {}).get("spdx_id"),
                "topics": metadata.get("topics", []),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "pushed_at": metadata.get("pushed_at"),
                "size_kb": metadata.get("size", 0),
                "archived": metadata.get("archived", False),
                "visibility": metadata.get("visibility", "public"),
            },
            "languages": languages,
            "architecture": architecture,
            "activity": {
                "last_push": metadata.get("pushed_at"),
                "recent_commits": self._format_commits(commits_payload),
            },
            "tree": tree[:5000],
            "tree_truncated": len(tree) > 5000 or tree_payload.get("truncated", False),
            "file_count": len(files),
            "directory_count": len(directories),
            "source_file_count": len(source_files),
            "top_level": self._top_level(tree),
            "quality": {"score": score, "grade": grade, "issues": issues},
            "previews": [
                {
                    "path": item["path"],
                    "language": item["language"],
                    "size": item["size"],
                    "content": item["content"][:12000],
                }
                for item in previews
            ],
        }

    @staticmethod
    def _format_languages(language_bytes: dict[str, int]) -> list[dict[str, Any]]:
        total = sum(language_bytes.values()) or 1
        return [
            {
                "name": name,
                "bytes": amount,
                "percentage": round(amount * 100 / total, 1),
                "color": LANGUAGE_COLORS.get(name, "#8b5cf6"),
            }
            for name, amount in sorted(language_bytes.items(), key=lambda pair: pair[1], reverse=True)
        ]

    @staticmethod
    def _format_commits(commits_payload: Any) -> list[dict[str, Any]]:
        if not isinstance(commits_payload, list):
            return []
        commits: list[dict[str, Any]] = []
        for item in commits_payload[:6]:
            commit_data = item.get("commit", {})
            commit_author = commit_data.get("author", {}) or {}
            author = item.get("author") or {}
            commits.append(
                {
                    "sha": item.get("sha", "")[:7],
                    "message": (commit_data.get("message") or "No commit message").splitlines()[0][:120],
                    "author": author.get("login") or commit_author.get("name") or "Unknown contributor",
                    "avatar_url": author.get("avatar_url"),
                    "date": commit_author.get("date"),
                    "html_url": item.get("html_url"),
                }
            )
        return commits

    @staticmethod
    def _top_level(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        types: dict[str, str] = {}
        for item in tree:
            root = item["path"].split("/", 1)[0]
            counts[root] += 1
            types[root] = "directory" if "/" in item["path"] or item["type"] == "directory" else "file"
        return [
            {"name": name, "type": types[name], "items": count}
            for name, count in counts.most_common(12)
        ]

    @staticmethod
    def _find_quality_issues(previews: list[dict[str, Any]], tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for file in previews:
            content = file["content"]
            path = file["path"]
            if re.search(r"\b(TODO|FIXME)\b", content, re.IGNORECASE):
                issues.append(_quality_issue("low", "Unresolved work marker", "TODO/FIXME markers suggest unfinished paths worth reviewing.", path))
            if re.search(r"\b(eval|exec)\s*\(", content) or "dangerouslySetInnerHTML" in content:
                issues.append(_quality_issue("high", "Dynamic code or HTML execution", "Review dynamic execution because untrusted input can become a security issue.", path))
            if re.search(r"except\s+Exception\s*:", content) or re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", content):
                issues.append(_quality_issue("medium", "Broad error handling", "A broad or empty catch can hide the original failure and make incidents harder to diagnose.", path))
            if re.search(r"console\.log\s*\(", content) or re.search(r"\bprint\s*\(", content):
                issues.append(_quality_issue("low", "Debug output in source", "Consider replacing debug output with structured, environment-aware logging.", path))
            if len(content.splitlines()) > 800:
                issues.append(_quality_issue("medium", "Large source module", "Large modules are harder to test and navigate; consider extracting cohesive responsibilities.", path))

        if not any(item["path"].lower().endswith(("readme.md", "readme")) for item in tree):
            issues.append(_quality_issue("low", "Missing README", "A README would make the project easier for new contributors to understand."))
        if not any("test" in item["path"].lower() for item in tree):
            issues.append(_quality_issue("medium", "No obvious test suite", "No test directory or test-named file was found in the repository tree."))
        return issues[:12]
