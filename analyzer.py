"""Safe, deterministic GitHub repository analyzer.

The analyzer only reads GitHub's REST API. It never checks out or executes code.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import os
import re
import time
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    tomllib = None


class GitHubAPIError(RuntimeError):
    """An actionable error returned while reading GitHub."""


def validate_github_url(url: str) -> Tuple[str, str]:
    """Return ``(owner, repo)`` for a public github.com repository URL."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("repository URL is required")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("URL must use https://github.com/<owner>/<repo>")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or any(p in {".", ".."} for p in parts):
        raise ValueError("URL must identify exactly one GitHub repository")
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[0]) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid GitHub owner or repository name")
    return parts[0], repo


class _GitHub:
    def __init__(self, token: Optional[str] = None, timeout: float = 15):
        self.token, self.timeout = token or os.getenv("GITHUB_TOKEN"), timeout

    def get(self, path: str) -> Any:
        request = Request("https://api.github.com" + path, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "RepoPilot/1.0",
            **({"Authorization": "Bearer " + self.token} if self.token else {}),
        })
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = "rate limit exceeded" if exc.code in {403, 429} else f"HTTP {exc.code}"
            if exc.code == 404:
                detail = "repository not found or is not public"
            raise GitHubAPIError(f"GitHub API error: {detail}") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise GitHubAPIError(f"GitHub API unavailable: {exc}") from exc


SECRET_PATTERNS = [
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_\-]{20,}"), "high"),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), "high"),
    ("generic_secret_assignment", re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?([A-Za-z0-9_\-/+=]{12,})"), "medium"),
]


def _redact(value: str) -> str:
    return value[:4] + "…[REDACTED]" if len(value) > 4 else "[REDACTED]"


def _secret_findings(path: str, text: str) -> List[Dict[str, Any]]:
    findings = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for kind, pattern, confidence in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                secret = match.group(1) if kind == "generic_secret_assignment" and match.lastindex else match.group(0)
                findings.append({"type": "secret", "kind": kind, "path": path, "line": line_no,
                                 "confidence": confidence, "evidence": line.replace(secret, _redact(secret)),
                                 "limitation": "Pattern-based detection; review context and rotate exposed credentials."})
    return findings


def _finding(kind: str, title: str, path: str, line: Optional[int], confidence: str, evidence: str, limitation: str = "") -> Dict[str, Any]:
    return {"type": kind, "title": title, "path": path, "line": line, "confidence": confidence,
            "evidence": evidence, "limitation": limitation}


def _score(checks: Dict[str, bool]) -> Dict[str, Any]:
    criteria = {"documentation": (checks["readme"], 20), "license": (checks["license"], 10),
                "tests": (checks["tests"], 25), "configuration": (checks["config"], 15),
                "source": (checks["source"], 30)}
    earned = sum(weight for present, weight in criteria.values() if present)
    return {"score": earned, "max": 100, "criteria": {
        name: {"met": present, "points": weight if present else 0, "max_points": weight}
        for name, (present, weight) in criteria.items()}}


def _architecture(paths: Iterable[str]) -> List[Dict[str, Any]]:
    """Build a bounded, evidence-only directory tree for the UI."""
    nodes: Dict[str, Dict[str, Any]] = {}
    for path in sorted(paths):
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            current = "/".join(parts[:index])
            nodes.setdefault(current, {
                "path": current,
                "kind": "file" if index == len(parts) else "directory",
                "children": [],
            })
            if index > 1:
                parent = "/".join(parts[:index - 1])
                if current not in nodes[parent]["children"]:
                    nodes[parent]["children"].append(current)
    return [node for path, node in nodes.items() if "/" not in path]


def _languages_from_paths(paths: Iterable[str]) -> Dict[str, int]:
    extensions = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".css": "CSS", ".html": "HTML"}
    counts: Dict[str, int] = {}
    for path in paths:
        language = extensions.get(os.path.splitext(path.lower())[1])
        if language:
            counts[language] = counts.get(language, 0) + 1
    return counts


def _dependency_insights(files: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract declared dependencies without claiming vulnerability status."""
    items: List[Dict[str, Any]] = []
    manifests: List[str] = []

    def add(name: str, spec: Any, ecosystem: str, manifest: str, group: str = "runtime") -> None:
        name = str(name).strip()
        if name:
            items.append({"name": name, "spec": str(spec or "*"), "ecosystem": ecosystem,
                          "manifest": manifest, "group": group})

    for item in files:
        path, content = item.get("path", ""), item.get("content")
        if not isinstance(content, str):
            continue
        basename = os.path.basename(path).lower()
        if basename == "package.json":
            try:
                payload = json.loads(content)
            except (TypeError, ValueError):
                continue
            manifests.append(path)
            for group in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                values = payload.get(group) or {}
                if not isinstance(values, dict):
                    continue
                for name, spec in values.items():
                    add(name, spec, "npm", path, "development" if group == "devDependencies" else "runtime")
        elif basename in {"requirements.txt", "requirements-dev.txt", "requirements.lock"}:
            manifests.append(path)
            for line in content.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith(("-", "git+", "http:", "https:")):
                    continue
                match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", line)
                if match:
                    add(match.group(1), match.group(2).strip() or "*", "PyPI", path)
        elif basename == "pyproject.toml" and tomllib is not None:
            try:
                payload = tomllib.loads(content)
            except (tomllib.TOMLDecodeError, ValueError):
                continue
            dependencies = payload.get("project", {}).get("dependencies", [])
            for dependency in dependencies:
                match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", str(dependency))
                if match:
                    add(match.group(1), match.group(2).strip() or "*", "PyPI", path)
            for name, spec in (payload.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}).items():
                if name.lower() != "python":
                    add(name, spec if isinstance(spec, str) else json.dumps(spec, sort_keys=True), "PyPI", path)
            manifests.append(path)
        elif basename == "cargo.toml" and tomllib is not None:
            try:
                payload = tomllib.loads(content)
            except (tomllib.TOMLDecodeError, ValueError):
                continue
            # TOML tables use dotted keys in the parsed representation.
            for group in ("dependencies", "dev-dependencies", "build-dependencies"):
                for name, spec in (payload.get(group, {}) or {}).items():
                    add(name, spec if isinstance(spec, str) else json.dumps(spec, sort_keys=True), "crates.io", path, group)
            manifests.append(path)
        elif basename == "go.mod":
            requires = False
            for line in content.splitlines():
                match = re.match(r"^\s*(?:require\s+)?([^\s]+)\s+(v[^\s]+)", line)
                if match and match.group(1) not in {"module", "go"}:
                    add(match.group(1), match.group(2), "Go", path)
                    requires = True
            if requires:
                manifests.append(path)

    unique = {(entry["ecosystem"], entry["name"], entry["manifest"], entry["group"]): entry for entry in items}
    items = sorted(unique.values(), key=lambda entry: (entry["ecosystem"], entry["name"].lower()))
    ecosystems = sorted({entry["ecosystem"] for entry in items})
    return {"manifests": sorted(set(manifests)), "items": items, "count": len(items), "ecosystems": ecosystems,
            "limitation": "Declared dependencies are listed for orientation; no vulnerability or freshness claim is made."}


def _result_from_files(repository_url: str, metadata: Dict[str, Any], files: List[Dict[str, Any]], languages: Dict[str, int], *, tree_truncated: bool, source_note: str = "") -> Dict[str, Any]:
    paths = {f["path"] for f in files}
    lower = {p.lower() for p in paths}
    frameworks = _frameworks(paths)
    docs = {"readme": any(p.startswith("readme") for p in lower), "license": any(p.startswith("license") for p in lower), "contributing": any(p.startswith("contributing") for p in lower)}
    tests = sorted(p for p in paths if re.search(r"(^|/)(test|tests|spec|specs)(/|$)|(_test|\.test\.|\.spec\.)", p, re.I))
    configs = sorted(p for p in paths if os.path.basename(p).lower() in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "dockerfile", ".editorconfig"} or p.lower() in {".github/workflows/ci.yml", ".github/workflows/ci.yaml"})
    checks = {"readme": docs["readme"], "license": docs["license"], "tests": bool(tests), "config": bool(configs), "source": any(not _is_maintenance_file(p) for p in paths)}
    findings = [finding for item in files for finding in item.get("findings", [])]
    dependencies = _dependency_insights(files)
    if dependencies["count"] == 0:
        findings.append(_finding("dependencies", "No dependency manifest detected", "", None, "low",
                                 "No supported dependency manifest was found in the inspected files.",
                                 dependencies["limitation"]))
    if not docs["readme"]:
        findings.append(_finding("documentation", "README is missing", "", None, "high", "No README file in bounded tree."))
    if not tests:
        findings.append(_finding("tests", "No tests discovered", "", None, "medium", "No conventional test paths or filenames found.", "Heuristic discovery can miss project-specific test layouts."))
    findings.sort(key=lambda x: (0 if x["type"] == "secret" else 1, x.get("path", ""), x.get("line") or 0, x.get("title", "")))
    for finding in findings:
        finding["severity"] = "critical" if finding["type"] == "secret" and finding.get("confidence") == "high" else ("high" if finding["type"] == "secret" else ("medium" if finding["type"] == "tests" else "low"))
    return {"repository": repository_url, "metadata": {k: metadata.get(k) for k in ("full_name", "description", "private", "default_branch", "stargazers_count", "forks_count", "open_issues_count", "html_url")},
            "limits": {"max_files": 200, "max_file_bytes": 100_000, "files_seen": len(files), "tree_truncated": tree_truncated},
            "files": [{k: v for k, v in item.items() if k != "findings"} for item in files], "architecture": _architecture(paths), "languages": dict(sorted(languages.items())), "frameworks": frameworks,
            "documentation": docs, "tests": {"files": tests, "found": bool(tests)}, "configs": configs,
            "dependencies": dependencies,
            "secret_findings": [f for f in findings if f["type"] == "secret"], "health": _score(checks), "findings": findings,
            "phases": ["Repository validated", "File structure retrieved", "Project signals detected", "Evidence verified", "Findings prioritized"],
            "methodology": {"Overall health": "Weighted indicator: README 20, license 10, recognized tests 25, project configuration 15, and source files 30. This is not a claim of software quality."},
            "limitations": [source_note or "Only bounded, read-only GitHub API inspection is performed.", "Pattern matches require human review and do not prove a secret is valid.", "Test discovery uses conventional names and may miss custom layouts."]}


class RepoAnalyzer:
    def __init__(self, *, max_files: int = 200, max_file_bytes: int = 100_000, timeout: float = 15,
                 token: Optional[str] = None, cache_ttl: float = 300):
        self.max_files, self.max_file_bytes = max_files, max_file_bytes
        self.api = _GitHub(token, timeout)
        self.cache_ttl = max(0, cache_ttl)
        self._analysis_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def analyze(self, repository_url: str, *, force_refresh: bool = False) -> Dict[str, Any]:
        owner, repo = validate_github_url(repository_url)
        cache_key = repository_url.strip().rstrip("/").lower()
        cached = self._analysis_cache.get(cache_key)
        if not force_refresh and self.cache_ttl > 0 and cached and time.monotonic() - cached[0] < self.cache_ttl:
            return copy.deepcopy(cached[1])
        base = f"/repos/{owner}/{repo}"
        try:
            metadata = self.api.get(base)
        except GitHubAPIError as exc:
            if "rate limit exceeded" in str(exc).lower():
                result = self._analyze_archive(owner, repo, repository_url)
                self._analysis_cache[cache_key] = (time.monotonic(), result)
                return copy.deepcopy(result)
            raise
        branch = metadata.get("default_branch") or "main"
        try:
            tree = self.api.get(base + f"/git/trees/{quote(branch, safe='')}?recursive=1")
        except GitHubAPIError as exc:
            if "rate limit exceeded" in str(exc).lower():
                result = self._analyze_archive(owner, repo, repository_url, branch=branch)
                self._analysis_cache[cache_key] = (time.monotonic(), result)
                return copy.deepcopy(result)
            raise
        entries = sorted((e for e in tree.get("tree", []) if e.get("type") == "blob"), key=lambda e: e.get("path", ""))[: self.max_files]
        files: List[Dict[str, Any]] = []
        all_findings: List[Dict[str, Any]] = []
        for entry in entries:
            path, size = entry.get("path", ""), entry.get("size", 0)
            item: Dict[str, Any] = {"path": path, "size": size, "type": "file", "findings": []}
            if size <= self.max_file_bytes and not _likely_binary(path):
                try:
                    payload = self.api.get(base + "/contents/" + quote(path, safe=""))
                    raw = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
                    item["content"] = raw
                    item["findings"].extend(_secret_findings(path, raw))
                except GitHubAPIError:
                    item["content_error"] = "content unavailable"
            files.append(item)
        source_note = ""
        try:
            languages = self.api.get(base + "/languages")
        except GitHubAPIError as exc:
            if "rate limit exceeded" not in str(exc).lower():
                raise
            # The language endpoint is a separate API request. If only that
            # request is limited, keep the analysis useful by deriving a
            # conservative language map from the files already inspected.
            languages = _languages_from_paths([item["path"] for item in files])
            source_note = "GitHub API rate limit reached for language metadata; language counts are inferred from inspected file extensions."
        result = _result_from_files(
            repository_url,
            metadata,
            files,
            languages,
            tree_truncated=len(tree.get("tree", [])) > self.max_files,
            source_note=source_note,
        )
        self._analysis_cache[cache_key] = (time.monotonic(), result)
        return copy.deepcopy(result)

    def compare(self, repository_url: str, other_repository_url: str, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Compare two repository snapshots using the same bounded analyzer."""
        left, right = self.analyze(repository_url, force_refresh=force_refresh), self.analyze(other_repository_url, force_refresh=force_refresh)
        left_files = {item["path"]: item for item in left.get("files", [])}
        right_files = {item["path"]: item for item in right.get("files", [])}
        added = sorted(set(right_files) - set(left_files))
        removed = sorted(set(left_files) - set(right_files))
        modified = sorted(path for path in set(left_files) & set(right_files)
                          if left_files[path].get("content") != right_files[path].get("content")
                          or left_files[path].get("size") != right_files[path].get("size"))
        def dependency_names(result: Dict[str, Any]) -> set[str]:
            return {item["name"] for item in result.get("dependencies", {}).get("items", [])}
        left_deps, right_deps = dependency_names(left), dependency_names(right)
        return {"repositories": [repository_url, other_repository_url],
                "added_files": added, "removed_files": removed, "modified_files": modified,
                "dependency_changes": {"added": sorted(right_deps - left_deps), "removed": sorted(left_deps - right_deps)},
                "health": {"before": left.get("health", {}).get("score"), "after": right.get("health", {}).get("score"),
                           "delta": (right.get("health", {}).get("score", 0) - left.get("health", {}).get("score", 0))},
                "language_changes": {"before": left.get("languages", {}), "after": right.get("languages", {})},
                "summary": {"files_added": len(added), "files_removed": len(removed), "files_modified": len(modified)}}

    def _analyze_archive(self, owner: str, repo: str, repository_url: str, *, branch: str = "main") -> Dict[str, Any]:
        """Fallback for anonymous API rate limits using GitHub's public archive endpoint."""
        archive = None
        selected_branch = branch
        last_error: Optional[Exception] = None
        for candidate in (branch, "main", "master"):
            try:
                request = Request(f"https://github.com/{owner}/{repo}/archive/refs/heads/{quote(candidate, safe='')}.zip", headers={"User-Agent": "RepoPilot/1.0"})
                with urlopen(request, timeout=self.api.timeout) as response:
                    archive = response.read()
                selected_branch = candidate
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
        if archive is None:
            raise GitHubAPIError(f"GitHub API rate limit exceeded and repository archive unavailable: {last_error}") from last_error
        files: List[Dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = []
            for member in bundle.infolist():
                path = member.filename.split("/", 1)[-1] if "/" in member.filename else member.filename
                if not path or member.is_dir() or path.startswith("/") or ".." in path.split("/"):
                    continue
                members.append((path, member))
            members.sort(key=lambda pair: pair[0])
            for path, member in members[: self.max_files]:
                item: Dict[str, Any] = {"path": path, "size": member.file_size, "type": "file", "findings": []}
                if member.file_size <= self.max_file_bytes and not _likely_binary(path):
                    raw = bundle.read(member).decode("utf-8", "replace")
                    item["content"] = raw
                    item["findings"].extend(_secret_findings(path, raw))
                files.append(item)
            truncated = len(members) > self.max_files
        languages = _languages_from_paths([item["path"] for item in files])
        metadata = {"full_name": f"{owner}/{repo}", "description": "Metadata limited by GitHub API rate limits.", "default_branch": selected_branch, "html_url": f"https://github.com/{owner}/{repo}"}
        return _result_from_files(repository_url, metadata, files, languages, tree_truncated=truncated, source_note="GitHub API rate limit reached; analysis used the public source archive fallback. Metadata and language byte counts are approximate.")


def _likely_binary(path: str) -> bool:
    return os.path.splitext(path.lower())[1] in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2", ".exe", ".dll"}


def _is_maintenance_file(path: str) -> bool:
    return os.path.basename(path).lower() in {"readme.md", "license", "license.md", ".gitignore"}


def _frameworks(paths: Iterable[str]) -> List[str]:
    names = set(paths)
    lower = {p.lower() for p in names}
    found = []
    checks = [("Django", "manage.py" in lower or "django" in " ".join(lower)), ("Flask", "flask" in " ".join(lower)),
              ("FastAPI", "fastapi" in " ".join(lower)), ("React", "package.json" in lower and any("react" in p for p in lower)),
              ("Node.js", "package.json" in lower), ("Rust", "cargo.toml" in lower), ("Go", "go.mod" in lower)]
    for name, yes in checks:
        if yes: found.append(name)
    return sorted(found)


def to_markdown(result: Dict[str, Any]) -> str:
    """Export an analysis without exposing file contents or secret values."""
    meta, health = result["metadata"], result["health"]
    lines = [f"# RepoPilot report: {meta.get('full_name') or result['repository']}", "", f"Health score: **{health['score']}/{health['max']}**", "", "## Metadata", f"- {meta.get('description') or 'No description'}", f"- Default branch: `{meta.get('default_branch')}`", "", "## Languages", ", ".join(f"{k} ({v})" for k, v in result["languages"].items()) or "None", "", "## Frameworks", ", ".join(result["frameworks"]) or "None", "", "## Findings"]
    if not result["findings"]: lines.append("No findings.")
    for finding in result["findings"]:
        location = f" `{finding['path']}:{finding['line']}`" if finding.get("path") else ""
        lines.append(f"- **{finding.get('title', finding.get('kind', 'Secret'))}** ({finding['confidence']}){location}: {finding['evidence']}")
    return "\n".join(lines) + "\n"


analyze_repository = RepoAnalyzer().analyze


def compare_repositories(repository_url: str, other_repository_url: str, *, force_refresh: bool = False) -> Dict[str, Any]:
    """Convenience comparison API while retaining the legacy analyzer function."""
    return RepoAnalyzer().compare(repository_url, other_repository_url, force_refresh=force_refresh)
