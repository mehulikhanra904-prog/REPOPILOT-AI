import pytest

from analyzer import (_config_inventory, _dependency_inventory, _documentation_signals, _frameworks,
                      _result_from_files, RepoAnalyzer, _secret_findings, to_markdown, validate_github_url)


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


def test_bounded_content_drives_framework_and_config_signals_deterministically():
    paths = ["package.json", ".github/workflows/ci.yml", "README.md"]
    contents = {
        "package.json": '{"dependencies":{"react":"18.0.0","@angular/core":"17.0.0"},"scripts":{"test":"jest"}}',
        ".github/workflows/ci.yml": "jobs:\n  test:\n    runs-on: ubuntu-latest\n    steps: []\n",
        "README.md": "# Demo\n\n## Installation\n\n## Usage\n",
    }
    assert _frameworks(paths, contents) == ["Angular", "Node.js", "React"]
    inventory = _config_inventory(paths, contents)
    assert inventory[0]["kind"] == "GitHub Actions workflow"
    assert inventory[0]["content_signals"] == ["automation or development command"]
    assert inventory[1]["content_signals"] == ["automation or development command", "dependency or runtime declaration"]
    docs = _documentation_signals(paths, contents)
    assert docs["readme_quality"] == "strong"
    assert docs["readme_signals"] == ["installation or setup guidance", "usage or example guidance"]


def test_dependency_inventory_is_syntactic_and_stable():
    inventory = _dependency_inventory(
        ["package.json", "requirements.txt"],
        {"package.json": '{"dependencies":{"requests":"1"},"devDependencies":{"pytest":"2"}}',
         "requirements.txt": "requests==1\n# comment\npytest>=2\n"},
    )
    assert inventory == [
        {"path": "package.json", "ecosystem": "Node.js", "dependency_count": 2, "content_scanned": True,
         "limitation": "Manifest inventory is syntactic; it does not audit versions or vulnerabilities."},
        {"path": "requirements.txt", "ecosystem": "Python", "dependency_count": 2, "content_scanned": True,
         "limitation": "Manifest inventory is syntactic; it does not audit versions or vulnerabilities."},
    ]


def test_result_redacts_file_contents_and_explains_priorities_and_limits():
    result = _result_from_files(
        "https://github.com/a/b", {"full_name": "a/b", "default_branch": "main"},
        [{"path": "config.py", "size": 30, "type": "file", "content": "TOKEN='supersecretvalue123'\n",
          "findings": _secret_findings("config.py", "TOKEN='supersecretvalue123'\n")}], {}, tree_truncated=False,
        reproducibility={"commit_sha": "abc123", "tree_sha": "tree123"},
    )
    assert "content" not in result["files"][0]
    assert result["findings"][0]["priority_rationale"]
    report = to_markdown(result)
    assert "## Methodology" in report and "## Scan limits" in report
    assert "supersecretvalue123" not in report
