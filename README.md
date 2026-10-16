# RepoPilot AI

> **Understand your codebase. Discover what matters. Improve with confidence.**

RepoPilot AI is an evidence-first repository investigator for developers, maintainers, open-source contributors, and judges evaluating unfamiliar codebases. Give it a public GitHub repository URL and it builds a bounded, read-only review of the repository's structure, project signals, documentation, tests, configuration, dependencies, and potential secret patterns.

RepoPilot is intentionally not a generic chatbot. Its central promise is:

> **Every important conclusion should be tied to repository evidence, a transparent rule, and an explicit limitation.**

## Live demo and source

- **Live app:** [repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app](https://repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app/)
- **GitHub repository:** [mehulikhanra904-prog/REPOPILOT-AI](https://github.com/mehulikhanra904-prog/REPOPILOT-AI)
- **App entry point:** [`app.py`](app.py)

## Why RepoPilot exists

Understanding an unfamiliar repository usually means manually searching hundreds of files, guessing where the application starts, checking whether tests really exist, and deciding which warnings deserve attention first. RepoPilot turns that first investigation into a repeatable review surface.

It answers four practical questions:

1. **What is this repository made of?** — languages, frameworks, files, configuration, and architecture.
2. **What did the scan actually establish?** — evidence-backed observations with paths and line numbers where available.
3. **What should be reviewed first?** — deterministic severity and priority ordering.
4. **How reproducible is the result?** — branch, commit/tree metadata, scan limits, source, and limitations.

## Core features

### Evidence-backed findings

Findings include the evidence returned by the analyzer instead of unsupported claims. A finding can contain:

- Category and title
- Severity and confidence
- File path and line number, when available
- Redacted evidence for suspected secrets
- Priority rationale
- Recommended review context through limitations

Repository content is treated as untrusted data. README instructions and source comments cannot override the analyzer's safety rules.

### Fix-first prioritization

RepoPilot orders findings using deterministic rules:

1. High-confidence potential secret exposure is reviewed first.
2. Medium-impact test and documentation gaps follow.
3. Lower-confidence or lower-impact signals come later.

This is a triage aid, not a claim that the repository is secure or production-ready.

### Repository health signal

The health indicator is transparent and intentionally limited to documented repository signals:

| Criterion | Weight | What it checks |
| --- | ---: | --- |
| Documentation | 20 | A conventional README is present |
| License | 10 | A conventional license file is present |
| Tests | 25 | Conventional test directories or filenames are discoverable |
| Configuration | 15 | Recognized project/tooling configuration is present |
| Source | 30 | Non-maintenance project files are present |

The score is an indicator created by RepoPilot's rules. It is not a universal software-quality score.

### Reproducibility metadata

When GitHub API metadata is available, the report records:

- Repository name and URL
- Default branch
- Commit SHA and commit URL
- Git tree SHA
- Analysis source
- File and byte limits
- Whether the tree was truncated

When the anonymous GitHub API rate limit is reached, RepoPilot falls back to the public source ZIP archive and records that limitation in the report.

### Dependency and configuration inventory

The analyzer recognizes common manifests across Python, Node.js, Go, Rust, Ruby, and PHP projects. It reports syntactic manifest counts and configuration signals without installing packages or claiming vulnerability status.

### Documentation quality signals

The analyzer checks for a README, license, and contributing guide. It also searches a bounded README excerpt for installation, setup, usage, example, configuration, and environment-variable guidance.

### Professional review workspace

The Streamlit interface includes:

- Judge-facing landing page
- Local demo sign-in and account creation
- Workspace sidebar and active-review status
- Executive repository summary
- Health signal cards and score methodology
- Severity/category finding filters
- Expandable evidence cards
- Repository architecture map
- Analysis history for the current browser session
- Scope and limitations section
- Markdown report export

## Analysis workflow

1. **Repository intake** — validate an HTTPS `github.com/<owner>/<repo>` URL.
2. **Metadata retrieval** — retrieve the public repository and default branch.
3. **Snapshot identification** — record commit/tree metadata when available.
4. **Bounded reconnaissance** — collect at most 200 files by default and inspect files up to 100,000 bytes.
5. **Project signal detection** — detect languages, frameworks, configuration, manifests, tests, and documentation signals.
6. **Evidence inspection** — inspect bounded text windows without executing repository code.
7. **Finding verification** — preserve paths, lines, redaction, confidence, and limitations.
8. **Fix-first ordering** — sort findings using deterministic severity and stable path/line keys.
9. **Report generation** — show the dashboard and export a Markdown report.

## Safety and security

RepoPilot is designed for read-only inspection:

- It never checks out and executes repository code.
- It does not run tests, package installers, build scripts, Dockerfiles, or workflows from the submitted repository.
- It enforces bounded file-count and file-size limits.
- It skips common binary formats during text inspection.
- Suspected secrets are redacted before evidence is displayed or exported.
- Pattern matches do not prove a credential is valid; suspected credentials should be reviewed and rotated.
- Dependency inventory is syntactic and does not assert vulnerabilities.
- Public repository content is treated as untrusted input and potential prompt injection.

### Authentication limitation

The sign-in/create-account flow is **local demo authentication only**. Accounts and salted password hashes live in Streamlit session state and disappear when the session or app process ends. There is no database, account recovery, email verification, multi-user identity provider, or durable session store. Plaintext passwords are not stored, but this flow must not be used as production security.

## Project structure

```text
REPOPILOT-AI/
├── app.py              # Streamlit application and workspace UI
├── analyzer.py         # Safe GitHub analyzer and Markdown exporter
├── styles.css          # Product UI styling
├── test_analyzer.py    # Deterministic analyzer tests
├── requirements.txt    # Runtime and test dependencies
├── run_repopilot.bat   # Windows launcher
├── .gitignore
├── __init__.py
└── README.md
```

## Run locally

### Requirements

- Python 3.10 or newer
- Network access to GitHub for live analysis
- A public GitHub repository URL

### Windows

```bat
cd "Repopilot AI"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501).

You can also double-click `run_repopilot.bat`.

### macOS/Linux

```bash
cd "Repopilot AI"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

### Optional GitHub token

Anonymous GitHub API requests have a low rate limit. Set `GITHUB_TOKEN` to increase the limit:

```bat
set GITHUB_TOKEN=your_token
```

or on macOS/Linux:

```bash
export GITHUB_TOKEN=your_token
```

Never commit a token to this repository. The application still has a public ZIP archive fallback when the anonymous limit is reached.

## Testing and verification

Run syntax checks:

```bash
python -m py_compile app.py analyzer.py test_analyzer.py
```

Run the deterministic analyzer tests:

```bash
python -m pytest -q
```

The tests cover:

- GitHub URL validation
- Secret redaction
- Transparent health scoring
- Evidence paths and Markdown export
- Framework and configuration signals
- README quality signals
- Dependency manifest inventory
- Reproducibility metadata
- Finding priority rationale and scan limits

The live Streamlit app requires network access to GitHub. No repository code is executed during analysis.

## Deploy with Streamlit Community Cloud

1. Push this repository to GitHub.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Sign in with GitHub.
4. Create a new app from:

   ```text
   mehulikhanra904-prog/REPOPILOT-AI
   ```

5. Select branch `main`.
6. Set the main file to `app.py`.
7. Deploy.

The deployed app should use `requirements.txt` automatically. If you want higher GitHub API limits, add `GITHUB_TOKEN` through the deployment platform's secrets manager. Do not put secrets in source files.

## Demo script for judges

Use this short flow for a reliable demonstration:

1. Open the live app and create a local demo account.
2. Enter a public repository URL.
3. Show the real analysis phases and bounded scan result.
4. Point out the commit/branch/source metadata.
5. Open the executive summary and health methodology.
6. Filter findings by severity.
7. Expand one finding and show its evidence, location, confidence, and limitation.
8. Open the repository map.
9. Download the Markdown report.
10. Explain that the analyzer never executes submitted repository code.

The strongest product story is not “an AI found bugs.” It is “RepoPilot shows what it observed, why it prioritized it, and where the evidence came from.”

## Limitations and future scope

RepoPilot is an initial repository investigator, not a complete security scanner or software correctness proof. Known limitations include:

- Public repositories are currently the supported input.
- Scans are bounded by file count, file size, and signal-window limits.
- Test discovery uses conventional paths and names.
- Secret detection is pattern-based and can produce false positives or miss custom formats.
- Dependency inventory does not query an advisory database or assert vulnerabilities.
- Framework detection uses deterministic file names and bounded content signals.
- Archive fallback metadata is less complete than GitHub API metadata.
- Authentication is session-only demo authentication.

Potential future work includes trusted advisory integrations, richer language-specific checks, pull-request comparison, persistent report history, and isolated optional sandbox execution. Those features should preserve the current read-only and evidence-first safety model.

## OmniRush development note

RepoPilot was developed in the OmniRush.ai workspace as a focused, reproducible software project. The runtime application does not require a generative AI API: its core results come from bounded GitHub inspection and deterministic analysis rules. Any future AI-generated explanation layer should remain optional, clearly labeled, and grounded in the structured evidence returned by the analyzer.

## License

Add the license selected for your hackathon submission before distributing the project publicly. The current analyzer also reports whether the inspected target repository contains a conventional license file; that signal describes the target repository and is separate from this project's license.
