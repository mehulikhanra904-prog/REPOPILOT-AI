# RepoPilot AI

**Understand your codebase. Discover what matters. Improve with confidence.**

RepoPilot is an evidence-first repository investigator. Paste a public GitHub URL and it performs bounded, read-only inspection of the repository's metadata, file tree, languages, project signals, tests, documentation, configuration, and likely secret patterns. It then produces a transparent health indicator, a prioritized fix-first list, and a Markdown report.

## What is implemented

- HTTPS GitHub URL validation and graceful API/rate-limit errors
- Fixed-branch analysis with bounded file count and file-size limits
- Language and framework signal detection
- README quality signals, license/test/configuration discovery, and dependency manifest inventory
- Bounded manifest/source-content signals for framework and configuration detection
- Commit SHA, tree SHA, branch, and analysis-source metadata when GitHub provides it
- Redacted pattern-based secret review; source values are never exported
- Evidence references with paths, line numbers, priority rationale, confidence, and limitations
- Explainable weighted health score (README 20, license 10, tests 25, configuration 15, source 30)
- Fix-first severity ordering and architecture/file-tree data
- Markdown report download
- No repository code is checked out or executed
- Public archive fallback when anonymous GitHub API rate limits are reached
- Local demo sign-in and account creation with session-only salted password hashes

## Run locally

```bash
cd repopilot_ai
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Optional: set `GITHUB_TOKEN` to raise GitHub API limits. Never commit the token. If the anonymous API limit is reached, RepoPilot automatically uses GitHub's public source archive and marks that limitation in the report.

## Test and verify

```bash
python -m py_compile app.py analyzer.py test_analyzer.py
python -m pytest -q
```

The analyzer tests are deterministic unit tests. The live UI requires network access to `api.github.com`; it never executes files from the submitted repository.

## Limitations

This is an initial investigator, not a production security scanner or a proof of software quality. The report records the commit/tree snapshot when available, the analysis source, the weighted-score methodology, and scan limits so a result can be reproduced or qualified. Secret detection is pattern-based, test discovery follows conventional names, dependency inventory is syntactic and does not assert vulnerabilities, and the scan is bounded to keep public repositories safe and responsive. Framework, configuration, and README signals inspect only bounded file contents from the selected files; they can miss custom layouts or oversized/unavailable files.

### Authentication limitations

RepoPilot's sign-in experience is **local demo authentication only**. Accounts and salted password hashes live in Streamlit session state and are cleared when the session or app process ends; there is no database, account recovery, email verification, multi-user identity provider, or durable session store. Plaintext passwords are not stored, but this flow must not be presented as production security or used to protect sensitive data.
