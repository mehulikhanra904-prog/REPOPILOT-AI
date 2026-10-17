import base64

import pytest

from analyzer import GitHubAPIError, RepoAnalyzer, _dependency_insights, _secret_findings, to_markdown, validate_github_url


def test_validate_url_accepts_repo_and_rejects_unsafe_urls():
    assert validate_github_url("https://github.com/octo/demo.git") == ("octo", "demo")
    for value in ("http://github.com/a/b", "https://github.com/a", "https://evil.example/a/b", "https://github.com/a/b/issues"):
        with pytest.raises(ValueError):
            validate_github_url(value)


def test_secret_redaction_has_line_and_never_returns_secret():
    findings = _secret_findings("config.py", "TOKEN = 'supersecretvalue123'\n")
    assert findings and findings[0]["line"] == 1
    assert "supersecretvalue123" not in findings[0]["evidence"]
    assert "REDACTED" in findings[0]["evidence"]


def test_health_score_is_transparent_and_deterministic():
    result = {"score": 0}
    from analyzer import _score
    result = _score({"readme": True, "license": False, "tests": True, "config": False, "source": True})
    assert result["score"] == 75
    assert result["criteria"]["license"] == {"met": False, "points": 0, "max_points": 10}


def test_findings_include_evidence_paths_and_markdown_export():
    findings = _secret_findings(".env", "API_KEY=abcdefghijklmnop\n")
    assert findings[0]["path"] == ".env" and findings[0]["line"] == 1
    report = to_markdown({"repository": "https://github.com/a/b", "metadata": {"full_name": "a/b", "description": None, "default_branch": "main"}, "health": {"score": 10, "max": 100}, "languages": {}, "frameworks": [], "findings": findings})
    assert "a/b" in report and "abcdefghijklmnop" not in report


def test_language_rate_limit_falls_back_to_file_extensions():
    class FakeGitHub:
        def get(self, path):
            if path == "/repos/octo/demo":
                return {"full_name": "octo/demo", "default_branch": "main"}
            if path.startswith("/repos/octo/demo/git/trees/"):
                return {"tree": [{"type": "blob", "path": "app.py", "size": 10}]}
            if path == "/repos/octo/demo/contents/app.py":
                return {"content": base64.b64encode(b"print('ok')\n").decode()}
            if path == "/repos/octo/demo/languages":
                raise GitHubAPIError("GitHub API error: rate limit exceeded")
            raise AssertionError(f"Unexpected API path: {path}")

    analyzer = RepoAnalyzer()
    analyzer.api = FakeGitHub()
    result = analyzer.analyze("https://github.com/octo/demo")

    assert result["languages"] == {"Python": 1}
    assert any("inferred from inspected file extensions" in item for item in result["limitations"])


def test_dependency_insights_extracts_common_manifests_without_vulnerability_claims():
    files = [
        {"path": "package.json", "content": '{"dependencies":{"react":"^18.0.0"},"devDependencies":{"vitest":"^1"}}'},
        {"path": "requirements.txt", "content": "httpx>=0.27\n# ignored\n-r requirements-dev.txt\n"},
    ]
    result = _dependency_insights(files)
    assert result["count"] == 3
    assert {item["name"] for item in result["items"]} == {"react", "vitest", "httpx"}
    assert result["ecosystems"] == ["PyPI", "npm"]
    assert "vulnerability" in result["limitation"]


def test_analysis_cache_avoids_repeat_api_calls_and_can_refresh():
    class FakeGitHub:
        def __init__(self):
            self.calls = []

        def get(self, path):
            self.calls.append(path)
            if path == "/repos/octo/demo":
                return {"full_name": "octo/demo", "default_branch": "main"}
            if path.startswith("/repos/octo/demo/git/trees/"):
                return {"tree": [{"type": "blob", "path": "README.md", "size": 1}]}
            if path == "/repos/octo/demo/contents/README.md":
                return {"content": base64.b64encode(b"ok").decode()}
            if path == "/repos/octo/demo/languages":
                return {}
            raise AssertionError(path)

    api = FakeGitHub()
    analyzer = RepoAnalyzer(cache_ttl=60)
    analyzer.api = api
    analyzer.analyze("https://github.com/octo/demo")
    first_call_count = len(api.calls)
    analyzer.analyze("https://github.com/octo/demo")
    assert len(api.calls) == first_call_count
    analyzer.analyze("https://github.com/octo/demo", force_refresh=True)
    assert len(api.calls) > first_call_count


def test_compare_reports_file_dependency_and_health_changes_from_cached_snapshots():
    class FakeGitHub:
        def get(self, path):
            repo = "one" if "/one" in path else "two"
            if path == f"/repos/octo/{repo}":
                return {"full_name": f"octo/{repo}", "default_branch": "main"}
            if path.startswith(f"/repos/octo/{repo}/git/trees/"):
                names = ["README.md", "package.json"] if repo == "one" else ["README.md", "app.py", "package.json"]
                return {"tree": [{"type": "blob", "path": name, "size": 10} for name in names]}
            if path.endswith("/contents/README.md"):
                return {"content": base64.b64encode(b"readme").decode()}
            if path.endswith("/contents/app.py"):
                return {"content": base64.b64encode(b"print('ok')").decode()}
            if path.endswith("/contents/package.json"):
                content = '{"dependencies":{"a":"^1"}}' if repo == "one" else '{"dependencies":{"b":"^1"}}'
                return {"content": base64.b64encode(content.encode()).decode()}
            if path.endswith("/languages"):
                return {}
            raise AssertionError(path)

    analyzer = RepoAnalyzer()
    analyzer.api = FakeGitHub()
    comparison = analyzer.compare("https://github.com/octo/one", "https://github.com/octo/two")
    assert comparison["added_files"] == ["app.py"]
    assert comparison["dependency_changes"] == {"added": ["b"], "removed": ["a"]}
    assert comparison["health"]["after"] >= comparison["health"]["before"]
