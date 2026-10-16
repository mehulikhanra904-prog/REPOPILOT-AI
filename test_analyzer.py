import pytest

from analyzer import RepoAnalyzer, _secret_findings, to_markdown, validate_github_url


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
