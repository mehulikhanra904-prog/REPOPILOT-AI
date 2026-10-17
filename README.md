
### **Understand any repository. Explore the code. Fix the right things first.**

RepoPilot AI is an evidence-first GitHub repository investigator built with **Python** and **Streamlit**. Paste a public GitHub URL and get a focused view of the repository’s metadata, file structure, languages, framework signals, dependencies, tests, configuration, likely secret patterns, health score, and prioritized findings.

<p align="center">
  <a href="https://repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app/"><strong>🌐 Live Demo</strong></a>
  ·
  <a href="https://github.com/mehulikhanra904-prog/REPOPILOT-AI"><strong>View on GitHub</strong></a>
  ·
  <a href="#quick-start"><strong>Run locally</strong></a>
</p>

---

## 🌐 Live demo

Try the deployed Streamlit application:

**[Open RepoPilot AI →](https://repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app/)**

---

## ✨ What RepoPilot does

RepoPilot turns the first inspection of an unfamiliar repository into a repeatable workflow:

1. **Paste** a public GitHub repository URL.
2. **Inspect** bounded metadata, the default-branch tree, and project signals.
3. **Review** an explainable health indicator and fix-first findings.
4. **Open** architecture and file-tree evidence in the dashboard.
5. **Compare** repositories and identify file, dependency, language, and health changes.
6. **Download** Markdown, JSON, or filtered CSV reports for handoffs or follow-up work.

The analyzer is read-only: it does not clone, execute, or modify the submitted repository.

---

## 🎯 Features

| Feature | Description |
| --- | --- |
| **Repository overview** | Displays the repository, default branch, primary language, files analyzed, and open findings. |
| **Explainable health score** | Scores documentation, licensing, tests, configuration, and source signals with visible weights. |
| **Architecture map** | Builds a bounded evidence-only directory and file tree. |
| **Language detection** | Detects common languages from file extensions and GitHub metadata. |
| **Framework signals** | Looks for recognizable Django, Flask, FastAPI, React, Node.js, Rust, and Go markers. |
| **Test discovery** | Checks conventional test directories and filenames. |
| **Configuration discovery** | Finds common project, package, container, editor, and CI configuration files. |
| **Dependency insights** | Extracts declared packages from common npm, PyPI, Cargo, and Go manifests without claiming vulnerability status. |
| **Secret review** | Detects likely token and credential patterns while redacting values in evidence. |
| **Prioritized findings** | Orders findings by severity and includes paths, line numbers, confidence, and limitations. |
| **Markdown report** | Exports a report without exposing repository source contents or secret values. |
| **JSON and CSV exports** | Download the complete safe analysis as JSON or the filtered findings as CSV. |
| **Scan history** | Reopen up to 20 recent analyses during the current app process. |
| **Repository comparison** | Compare two repositories’ files, dependencies, languages, and health signals. |
| **Finding filters** | Filter findings by severity, confidence, and file type before reviewing or exporting them. |
| **Secure token settings** | Load an optional GitHub token from Streamlit secrets or `GITHUB_TOKEN` without displaying it. |
| **Theme toggle** | Switch between polished light and dark UI themes. |
| **Demo repository presets** | Launch one-click scans for Streamlit, FastAPI, React, and Next.js. |
| **Glassmorphism UI** | Uses a lavender glass interface, animated light background, soft gradients, responsive cards, and reduced-motion support. |
| **Rate-limit resilience** | Handles GitHub 403/429 limits, uses public archive fallback, and infers languages from inspected files when needed. |
| **Local demo auth** | Includes a session-only sign-in/create-account gate for the local Streamlit experience. |

---

## 🧭 Analysis pipeline

```text
Validate GitHub URL
        ↓
Read repository metadata
        ↓
Read the default-branch file tree
        ↓
Inspect bounded text files
        ↓
Detect languages, frameworks, tests, configs, and secret patterns
        ↓
Build evidence-backed findings
        ↓
Calculate the health score
        ↓
Display the dashboard and Markdown report
```

## 🎨 Interface experience

The current interface is designed for a polished presentation and judge-friendly demo:

- Lavender gradient background with subtle animated light movement
- Glassmorphism forms, metrics, cards, and evidence panels
- Responsive layout for desktop and smaller screens
- Light and deep-purple dark themes
- Clear primary actions, hover states, status badges, and progress feedback
- Accessible reduced-motion fallback for users who prefer less animation
- Repository presets for instant demonstrations without typing a URL

### Safety boundaries

- Only HTTPS `github.com/<owner>/<repository>` URLs are accepted.
- Analysis is read-only and repository code is never executed.
- At most **200 files** are inspected by default.
- Text-file inspection is limited to **100,000 bytes per file** by default.
- Binary files are skipped where appropriate.
- Secret evidence is redacted before it appears in the UI or report.
- Findings are review signals, not proof of a vulnerability or software quality.

---

## 📊 Health score methodology

The default score is a transparent repository-signal indicator, not a security audit:

| Signal | Weight |
| --- | ---: |
| README / documentation | 20 |
| License | 10 |
| Recognized tests | 25 |
| Project configuration | 15 |
| Source files | 30 |
| **Total** | **100** |

The dashboard explains the score methodology alongside the results.

---

## 🚀 Quick start

### Requirements

- Python **3.10+** recommended
- Internet access to GitHub
- A GitHub token is optional; anonymous analysis works until the public API rate limit is reached

### 1. Clone the repository

```bash
git clone https://github.com/mehulikhanra904-prog/REPOPILOT-AI.git
cd REPOPILOT-AI
```

### 2. Create a virtual environment

#### Windows PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Start the Streamlit app

```bash
streamlit run app.py
```

Open the local URL printed by Streamlit, normally:

```text
http://localhost:8501
```

#### Windows shortcut

```bat
run_repopilot.bat
```

---

## 🔐 Optional GitHub token

Set `GITHUB_TOKEN` to raise GitHub API limits. Never commit the token.

### PowerShell

```powershell
$env:GITHUB_TOKEN = "your-token"
streamlit run app.py
```

### macOS / Linux

```bash
export GITHUB_TOKEN="your-token"
streamlit run app.py
```

When the anonymous API limit is reached, RepoPilot attempts a public archive fallback and records that limitation in the report.

For Streamlit Cloud, add the token under **App settings → Secrets**. This is especially useful for avoiding GitHub 403/429 rate-limit responses:

```toml
github_token = "your-token"
```

The app never displays or includes the token in downloaded reports. Analysis results are cached for five minutes by default to reduce repeated GitHub API requests. Use the **GitHub token settings** panel in the sidebar to confirm whether a token is loaded without revealing its value.

---

## 🧪 Test and verify

Run the syntax check and deterministic analyzer tests:

```bash
python -m py_compile app.py analyzer.py test_analyzer.py
python -m pytest -q
```

Live repository analysis requires network access to `api.github.com`. Tests do not execute code from analyzed repositories.

---

## 🧩 Analyzer API

The analyzer can also be used directly from Python:

```python
from analyzer import RepoAnalyzer, analyze_repository, to_markdown

result = analyze_repository("https://github.com/owner/repository")
print(result["health"])
print(to_markdown(result))
```

For custom bounds:

```python
from analyzer import RepoAnalyzer

analyzer = RepoAnalyzer(
    max_files=100,
    max_file_bytes=50_000,
    timeout=10,
)
result = analyzer.analyze("https://github.com/owner/repository")
```

The result includes metadata, limits, files, architecture, languages, frameworks, dependency insights, documentation signals, test signals, configurations, secret findings, health, findings, completed phases, methodology, and limitations.

---

## 🗂️ Project structure

```text
REPOPILOT-AI/
├── app.py                 # Streamlit UI, local demo auth, dashboard, report download
├── analyzer.py            # Safe GitHub API/archive analyzer and Markdown exporter
├── styles.css             # RepoPilot visual system and responsive styling
├── test_analyzer.py       # Deterministic analyzer tests
├── requirements.txt       # Application and test dependencies
├── run_repopilot.bat      # Windows launcher
├── backend/               # Earlier FastAPI integration preserved in the repository
├── frontend/              # Earlier React dashboard preserved in the repository
└── README.md              # Project documentation
```

---

## 🛡️ Authentication note

The Streamlit sign-in experience is **local demo authentication only**:

- Accounts live in a process-local Streamlit resource shared across browser sessions.
- Passwords are salted and hashed with PBKDF2-HMAC-SHA256.
- Accounts disappear when the app process restarts or redeploys.
- There is no database, account recovery, email verification, durable session, or identity provider.

Do not use this flow to protect sensitive data or present it as production security.

<img width="1448" height="918" alt="REPOPILOT-AI SS FIRST PAGE" src="https://github.com/user-attachments/assets/eb2f6059-661c-4c65-92a7-436c9e0af9cd" />
---

<p align="center">
  <strong>RepoPilot AI</strong><br />
  <em>See the repository clearly. Fix the right things first.</em>
</p>


<img width="1534" height="920" alt="repo overview" src="https://github.com/user-attachments/assets/1d482652-3cfb-4084-bd51-2755e9c0eb1e" />


<img width="1501" height="931" alt="comparision result" src="https://github.com/user-attachments/assets/f4cb9986-5030-43ad-a624-2c4ac2bdfe72" />



## ⚠️ Limitations

RepoPilot is an initial repository investigator, not a production security scanner or proof of software quality.

- Secret detection is pattern-based and can produce false positives or miss custom formats.
- A detected pattern does not prove a credential is valid or active.
- Test discovery follows conventional names and may miss custom layouts.
- Dependency vulnerabilities are not asserted without advisory data.
- Large repositories are intentionally bounded for safety and responsiveness.
- Metadata and language counts may be approximate when archive fallback is used.

Always review findings in context and rotate any real credential that may have been exposed.

---

## 🗺️ Roadmap ideas

- Configurable analysis profiles for different repository sizes
- More language, framework, and secret-pattern coverage
- Dependency advisory integration
- Comparison reports between repository revisions
- CI checks for health-score regressions
- Production-ready authentication and persistent scan history

---

## 📄 License

No license has been declared for this project yet. Add a `LICENSE` file before distributing or reusing the code under specific terms.

---





