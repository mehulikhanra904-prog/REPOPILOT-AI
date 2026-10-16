import pytest

from backend.app.github import GitHubRepositoryAnalyzer, architecture_for_tree, parse_repo_url
from backend.app.config import Settings


def test_parse_repo_url_accepts_https_and_git_suffix():
    assert parse_repo_url("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
    assert parse_repo_url("github.com/fastapi/fastapi") == ("fastapi", "fastapi")


def test_parse_repo_url_rejects_non_github_hosts():
    with pytest.raises(ValueError, match="github.com"):
        parse_repo_url("https://gitlab.com/example/repo")


def test_static_quality_scan_finds_actionable_signals():
    issues = GitHubRepositoryAnalyzer._find_quality_issues(
        [{"path": "src/app.py", "content": "# TODO: split this\ntry:\n  eval(user_input)\nexcept Exception:\n  pass\n", "size": 80}],
        [{"path": "src/app.py", "type": "file"}],
    )
    titles = {issue["title"] for issue in issues}
    assert "Unresolved work marker" in titles
    assert "Dynamic code or HTML execution" in titles
    assert "Broad error handling" in titles


def test_settings_origins_are_split():
    settings = Settings(allowed_origins="http://one,http://two")
    assert settings.origins == ["http://one", "http://two"]


def test_architecture_signals_detect_stack_layers_and_tests():
    tree = [
        {"path": "package.json", "type": "file"},
        {"path": "src/index.ts", "type": "file"},
        {"path": "tests/app.test.ts", "type": "file"},
        {"path": ".github/workflows/ci.yml", "type": "file"},
        {"path": "docs/architecture.md", "type": "file"},
    ]
    result = architecture_for_tree(tree, ["TypeScript"])
    assert "Node.js" in result["stacks"]
    assert "package.json" in result["entrypoints"]
    assert "src/index.ts" in result["entrypoints"]
    assert result["test_file_count"] == 1
    assert result["workflow_count"] == 1
    assert "src" in result["layers"]
