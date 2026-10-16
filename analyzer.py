"""Safe, deterministic GitHub repository analyzer.

The analyzer only reads GitHub's REST API. It never checks out or executes code.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


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
            detail = "rate limit exceeded" if exc.code == 403 else f"HTTP {exc.code}"
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

SIGNAL_BYTES = 100_000
DEPENDENCY_MANIFESTS = {
    "requirements.txt": "Python",
    "requirements-dev.txt": "Python",
    "pipfile": "Python",
    "pipfile.lock": "Python",
    "pyproject.toml": "Python",
    "poetry.lock": "Python",
    "package.json": "Node.js",
    "package-lock.json": "Node.js",
    "npm-shrinkwrap.json": "Node.js",
    "yarn.lock": "Node.js",
    "pnpm-lock.yaml": "Node.js",
    "go.mod": "Go",
    "go.sum": "Go",
    "cargo.toml": "Rust",
    "cargo.lock": "Rust",
    "gemfile": "Ruby",
    "gemfile.lock": "Ruby",
    "composer.json": "PHP",
    "composer.lock": "PHP",
}


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
                                 "limitation": "Pattern-based detection; review context and rotate exposed credentials.",
                                 "priority_rationale": "Potential credential exposure can enable unauthorized access and should be reviewed first."})
    return findings


def _finding(kind: str, title: str, path: str, line: Optional[int], confidence: str, evidence: str, limitation: str = "") -> Dict[str, Any]:
    limitation = limitation or "Heuristic evidence should be reviewed against the repository context."
    return {"type": kind, "title": title, "path": path, "line": line, "confidence": confidence,
            "evidence": evidence, "limitation": limitation,
            "priority_rationale": "Prioritized for review based on its likely impact and the strength of the available evidence."}


def _bounded_contents(contents: Optional[Dict[str, str]], path: str) -> str:
    """Return at most the configured signal window for one repository file."""
    if not contents:
        return ""
    return str(contents.get(path, ""))[:SIGNAL_BYTES]


def _documentation_signals(paths: Iterable[str], contents: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Inspect documentation names and a bounded README excerpt without exporting it."""
    ordered = sorted(set(paths))
    lower = {path.lower(): path for path in ordered}
    readme_path = next((path for name, path in lower.items() if os.path.basename(name).startswith("readme")), None)
    readme = _bounded_contents(contents, readme_path) if readme_path else ""
    headings = re.findall(r"(?im)^\s*#{1,6}\s+([^\n#]+)", readme)
    heading_text = " ".join(headings).lower()
    signals = []
    if re.search(r"(?i)\b(install|installation|setup|getting started)\b", heading_text + " " + readme):
        signals.append("installation or setup guidance")
    if re.search(r"(?i)\b(usage|quickstart|example|examples|run)\b", heading_text + " " + readme):
        signals.append("usage or example guidance")
    if re.search(r"(?i)\b(configuration|config|environment variables|env)\b", heading_text + " " + readme):
        signals.append("configuration guidance")
    license_present = any(os.path.basename(path).lower().startswith("license") for path in ordered)
    contributing_present = any(os.path.basename(path).lower().startswith("contributing") for path in ordered)
    return {
        "readme": bool(readme_path),
        "readme_path": readme_path,
        "readme_signals": signals,
        "readme_quality": "strong" if len(signals) >= 2 else ("basic" if readme_path else "missing"),
        "license": license_present,
        "contributing": contributing_present,
    }


def _config_inventory(paths: Iterable[str], contents: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Classify recognized configuration files using bounded content evidence."""
    inventory = []
    for path in sorted(set(paths)):
        name = os.path.basename(path).lower()
        lower_path = path.lower()
        kind = None
        if name in {"pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini"}:
            kind = "Python project/tooling"
        elif name in {"package.json", ".npmrc", ".yarnrc", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
            kind = "Node.js project/tooling"
        elif name in {"cargo.toml", "cargo.lock"}:
            kind = "Rust project/tooling"
        elif name in {"go.mod", "go.sum"}:
            kind = "Go module"
        elif name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            kind = "Container"
        elif lower_path.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
            kind = "GitHub Actions workflow"
        elif name == ".editorconfig":
            kind = "Editor settings"
        elif name in {".env.example", ".env.sample", "config.example.json"}:
            kind = "Example environment/configuration"
        if kind:
            text = _bounded_contents(contents, path)
            signals = []
            if text:
                if re.search(r"(?im)^\s*(scripts|tool\.\w+|\[tool\.|\[project\])", text):
                    signals.append("tool/project metadata")
                if re.search(r"(?i)\b(test|lint|build|deploy|ci)\b", text):
                    signals.append("automation or development command")
                if re.search(r"(?i)\b(dependencies|require|uses|image|services)\b", text):
                    signals.append("dependency or runtime declaration")
            inventory.append({"path": path, "kind": kind, "content_signals": signals})
    return inventory


def _dependency_inventory(paths: Iterable[str], contents: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Inventory dependency manifests; counts are heuristic and never claim vulnerability status."""
    inventory = []
    for path in sorted(set(paths)):
        ecosystem = DEPENDENCY_MANIFESTS.get(os.path.basename(path).lower())
        if not ecosystem:
            continue
        text = _bounded_contents(contents, path)
        count = 0
        if text:
            if os.path.basename(path).lower() == "package.json":
                try:
                    package = json.loads(text)
                    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                        value = package.get(section, {}) if isinstance(package, dict) else {}
                        if isinstance(value, dict):
                            count += len(value)
                except (TypeError, ValueError):
                    count = len(re.findall(r"(?m)^\s*[\"']?[A-Za-z0-9_.@/-]+[\"']?\s*:", text))
            elif os.path.basename(path).lower() in {"go.mod", "cargo.toml", "pyproject.toml"}:
                count = len(re.findall(r"(?m)^\s*[A-Za-z0-9_.@/-]+\s*(?:=|\^|~|>=|<=|>|<)", text))
            else:
                count = len([line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", ";", "["))])
        inventory.append({"path": path, "ecosystem": ecosystem, "dependency_count": count,
                          "content_scanned": bool(text), "limitation": "Manifest inventory is syntactic; it does not audit versions or vulnerabilities."})
    return inventory


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


def _result_from_files(repository_url: str, metadata: Dict[str, Any], files: List[Dict[str, Any]], languages: Dict[str, int], *, tree_truncated: bool, source_note: str = "", reproducibility: Optional[Dict[str, Any]] = None, max_files: int = 200, max_file_bytes: int = 100_000) -> Dict[str, Any]:
    paths = {f["path"] for f in files}
    lower = {p.lower() for p in paths}
    contents = {f["path"]: f.get("content", "") for f in files if isinstance(f.get("content", ""), str)}
    frameworks = _frameworks(paths, contents)
    docs = _documentation_signals(paths, contents)
    tests = sorted(p for p in paths if re.search(r"(^|/)(test|tests|spec|specs)(/|$)|(_test|\.test\.|\.spec\.)", p, re.I))
    config_inventory = _config_inventory(paths, contents)
    configs = [item["path"] for item in config_inventory]
    dependencies = _dependency_inventory(paths, contents)
    checks = {"readme": docs["readme"], "license": docs["license"], "tests": bool(tests), "config": bool(configs), "source": any(not _is_maintenance_file(p) for p in paths)}
    findings = [finding for item in files for finding in item.get("findings", [])]
    if not docs["readme"]:
        findings.append(_finding("documentation", "README is missing", "", None, "high", "No README file in bounded tree.", "The bounded tree cannot verify project purpose, setup, or usage without a README."))
    elif not docs["readme_signals"]:
        findings.append(_finding("documentation", "README has limited project guidance", docs["readme_path"] or "", None, "low", "No installation, usage, or configuration signal was found in the bounded README excerpt.", "Heuristic README signals can miss equivalent wording or content beyond the bounded excerpt."))
    if not docs["license"]:
        findings.append(_finding("documentation", "License is missing", "", None, "medium", "No conventional license file in bounded tree.", "A license may be declared in metadata or under a non-standard filename."))
    if not tests:
        findings.append(_finding("tests", "No tests discovered", "", None, "medium", "No conventional test paths or filenames found.", "Heuristic discovery can miss project-specific test layouts."))
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for finding in findings:
        finding["severity"] = "critical" if finding["type"] == "secret" and finding.get("confidence") == "high" else ("high" if finding["type"] == "secret" else ("medium" if finding["type"] in {"tests", "documentation"} and finding.get("confidence") != "low" else "low"))
        finding.setdefault("priority_rationale", "Prioritized for review based on its likely impact and the strength of the available evidence.")
    findings.sort(key=lambda x: (priority_order.get(x.get("severity", "low"), 9), x.get("path", ""), x.get("line") or 0, x.get("title", x.get("kind", ""))))
    repro = dict(reproducibility or {})
    repro.setdefault("source", "github_api")
    repro.setdefault("default_branch", metadata.get("default_branch"))
    metadata_out = {k: metadata.get(k) for k in ("full_name", "description", "private", "default_branch", "stargazers_count", "forks_count", "open_issues_count", "html_url")}
    if repro.get("commit_sha"):
        metadata_out["commit_sha"] = repro["commit_sha"]
    if repro.get("tree_sha"):
        metadata_out["tree_sha"] = repro["tree_sha"]
    return {"repository": repository_url, "metadata": metadata_out, "reproducibility": repro,
            "limits": {"max_files": max_files, "max_file_bytes": max_file_bytes, "signal_bytes_per_file": SIGNAL_BYTES, "files_seen": len(files), "tree_truncated": tree_truncated},
            "files": [{k: v for k, v in item.items() if k not in {"findings", "content"}} for item in files], "architecture": _architecture(paths), "languages": dict(sorted(languages.items())), "frameworks": frameworks,
            "documentation": docs, "tests": {"files": tests, "found": bool(tests)}, "configs": configs, "config_inventory": config_inventory, "dependencies": dependencies,
            "secret_findings": [f for f in findings if f["type"] == "secret"], "health": _score(checks), "findings": findings,
            "phases": ["Repository validated", "File structure retrieved", "Project signals detected", "Evidence verified", "Findings prioritized"],
            "methodology": {"Overall health": "Weighted indicator: README 20, license 10, recognized tests 25, project configuration 15, and source files 30. This is not a claim of software quality.", "Evidence": "Frameworks, configuration, dependencies, and README signals use deterministic names plus bounded text excerpts from files already selected for inspection.", "Prioritization": "Findings are ordered by severity, then stable path and line keys. Secret exposure is first because its potential impact is highest; confidence describes pattern strength, not exploitability."},
            "limitations": [source_note or "Only bounded, read-only GitHub API inspection is performed.", "Commit SHA is recorded only when GitHub commit metadata is available; archive fallback records its branch and URL instead.", f"At most {max_files} files and {max_file_bytes} bytes per file are inspected; signal extraction also uses a {SIGNAL_BYTES}-byte per-file window.", "Pattern matches require human review and do not prove a secret is valid.", "Dependency inventory is syntactic and does not assert vulnerabilities or install packages.", "Test discovery uses conventional names and may miss custom layouts."]}


class RepoAnalyzer:
    def __init__(self, *, max_files: int = 200, max_file_bytes: int = 100_000, timeout: float = 15, token: Optional[str] = None):
        self.max_files, self.max_file_bytes = max_files, max_file_bytes
        self.api = _GitHub(token, timeout)

    def analyze(self, repository_url: str) -> Dict[str, Any]:
        owner, repo = validate_github_url(repository_url)
        base = f"/repos/{owner}/{repo}"
        try:
            metadata = self.api.get(base)
        except GitHubAPIError as exc:
            if "rate limit exceeded" in str(exc).lower():
                return self._analyze_archive(owner, repo, repository_url)
            raise
        branch = metadata.get("default_branch") or "main"
        try:
            tree = self.api.get(base + f"/git/trees/{quote(branch, safe='')}?recursive=1")
        except GitHubAPIError as exc:
            if "rate limit exceeded" in str(exc).lower():
                return self._analyze_archive(owner, repo, repository_url, branch=branch)
            raise
        commit: Optional[Dict[str, Any]] = None
        try:
            commit = self.api.get(base + f"/commits/{quote(branch, safe='')}")
        except GitHubAPIError as exc:
            if "rate limit exceeded" in str(exc).lower():
                return self._analyze_archive(owner, repo, repository_url, branch=branch)
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
        languages = self.api.get(base + "/languages")
        repro = {"source": "github_api", "commit_sha": commit.get("sha") if commit else None,
                 "commit_url": commit.get("html_url") if commit else None, "tree_sha": tree.get("sha"),
                 "default_branch": branch}
        return _result_from_files(repository_url, metadata, files, languages, tree_truncated=len(tree.get("tree", [])) > self.max_files,
                                   reproducibility=repro, max_files=self.max_files, max_file_bytes=self.max_file_bytes)

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
        return _result_from_files(repository_url, metadata, files, languages, tree_truncated=truncated,
                                  source_note="GitHub API rate limit reached; analysis used the public source archive fallback. Metadata and language byte counts are approximate.",
                                  reproducibility={"source": "public_archive", "archive_branch": selected_branch,
                                                    "archive_url": f"https://github.com/{owner}/{repo}/archive/refs/heads/{quote(selected_branch, safe='')}.zip",
                                                    "commit_sha": None, "default_branch": selected_branch},
                                  max_files=self.max_files, max_file_bytes=self.max_file_bytes)


def _likely_binary(path: str) -> bool:
    return os.path.splitext(path.lower())[1] in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2", ".exe", ".dll"}


def _is_maintenance_file(path: str) -> bool:
    return os.path.basename(path).lower() in {"readme.md", "license", "license.md", ".gitignore"}


def _frameworks(paths: Iterable[str], contents: Optional[Dict[str, str]] = None) -> List[str]:
    """Detect frameworks from stable paths and bounded manifest/source excerpts."""
    names = set(paths)
    lower = {p.lower() for p in names}
    path_blob = " ".join(sorted(lower))
    manifest_text = "\n".join(_bounded_contents(contents, path) for path in sorted(names)
                               if os.path.basename(path).lower() in DEPENDENCY_MANIFESTS)[:SIGNAL_BYTES * 4]
    package_names = set()
    package_text = _bounded_contents(contents, next((p for p in names if os.path.basename(p).lower() == "package.json"), ""))
    if package_text:
        try:
            package = json.loads(package_text)
            for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                values = package.get(section, {}) if isinstance(package, dict) else {}
                if isinstance(values, dict):
                    package_names.update(str(name).lower() for name in values)
        except (TypeError, ValueError):
            package_names.update(re.findall(r"[\"'](@?[a-z0-9._/-]+)[\"']\s*:", package_text.lower()))
    python_text = "\n".join(_bounded_contents(contents, path) for path in sorted(names)
                              if path.lower().endswith((".py", ".toml", ".txt")))[:SIGNAL_BYTES * 4]
    found = set()
    if "manage.py" in lower or re.search(r"(?i)django", path_blob) or re.search(r"(?i)\bdjango\b", python_text):
        found.add("Django")
    if re.search(r"(?i)flask", path_blob) or re.search(r"(?i)\bflask\b", python_text):
        found.add("Flask")
    if re.search(r"(?i)fastapi", path_blob) or re.search(r"(?i)\bfastapi\b", python_text):
        found.add("FastAPI")
    if "package.json" in lower and ("react" in package_names or "react" in path_blob or re.search(r"(?i)[\"']react[\"']\s*[:=]", manifest_text)):
        found.add("React")
    if "next" in package_names or "next.js" in manifest_text.lower():
        found.add("Next.js")
    if "vue" in package_names:
        found.add("Vue")
    if "@angular/core" in package_names or "angular" in package_names:
        found.add("Angular")
    if "package.json" in lower:
        found.add("Node.js")
    if "cargo.toml" in lower:
        found.add("Rust")
    if "go.mod" in lower:
        found.add("Go")
    return sorted(found)


def to_markdown(result: Dict[str, Any]) -> str:
    """Export an analysis without exposing file contents or secret values."""
    meta, health = result.get("metadata", {}), result.get("health", {})
    lines = [f"# RepoPilot report: {meta.get('full_name') or result.get('repository', 'repository')}", "", f"Health score: **{health.get('score', 0)}/{health.get('max', 100)}**", "", "## Metadata", f"- {meta.get('description') or 'No description'}", f"- Default branch: `{meta.get('default_branch')}`"]
    repro = result.get("reproducibility", {})
    if repro.get("commit_sha"):
        lines.append(f"- Commit: `{repro['commit_sha']}`" + (f" ([view commit]({repro['commit_url']}))" if repro.get("commit_url") else ""))
    if repro.get("tree_sha"):
        lines.append(f"- Tree snapshot: `{repro['tree_sha']}`")
    lines.extend([f"- Analysis source: `{repro.get('source', 'github_api')}`", "", "## Languages", ", ".join(f"{k} ({v})" for k, v in result.get("languages", {}).items()) or "None", "", "## Frameworks", ", ".join(result.get("frameworks", [])) or "None"])
    dependencies = result.get("dependencies", [])
    lines.extend(["", "## Dependency manifests"])
    lines.extend([f"- `{item.get('path')}` — {item.get('ecosystem')} ({item.get('dependency_count', 0)} declared entries)" for item in dependencies] or ["None detected."])
    lines.extend(["", "## Findings"])
    findings = result.get("findings", [])
    if not findings:
        lines.append("No findings.")
    for finding in findings:
        location = f" `{finding['path']}:{finding['line']}`" if finding.get("path") else ""
        lines.append(f"- **{finding.get('title', finding.get('kind', 'Secret'))}** [{finding.get('severity', 'review')}; confidence: {finding.get('confidence', 'unknown')}]" + f"{location}: {finding.get('evidence', '')}")
        if finding.get("priority_rationale"):
            lines.append(f"  - Priority rationale: {finding['priority_rationale']}")
        if finding.get("limitation"):
            lines.append(f"  - Limitation: {finding['limitation']}")
    lines.extend(["", "## Methodology"])
    for name, explanation in result.get("methodology", {}).items():
        lines.append(f"- **{name}:** {explanation}")
    lines.extend(["", "## Scan limits"])
    for limitation in result.get("limitations", []):
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


analyze_repository = RepoAnalyzer().analyze
