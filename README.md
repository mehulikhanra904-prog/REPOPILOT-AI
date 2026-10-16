# ✦ RepoPilot AI

### **Understand any repository. Explore the code. Ship with confidence.**

RepoPilot AI is a polished repository-intelligence workspace for developers. Paste a public GitHub URL and get an explorable map of the project’s architecture, language composition, source tree, static quality signals, recent activity, and the questions that matter.

It combines a **React + Vite dashboard**, a **FastAPI backend**, GitHub’s REST API, and optional provider-neutral AI explanations — while keeping provider credentials on the server instead of in the browser.

<p align="center">
  <a href="https://repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app/"><strong>🌐 Live Demo</strong></a>
  ·
  <a href="https://github.com/mehulikhanra904-prog/REPOPILOT-AI"><strong>View on GitHub</strong></a>
  ·
  <a href="#quick-start"><strong>Run locally</strong></a>
</p>

---

## 🌐 Live demo

Try RepoPilot AI in your browser:

**[Open the RepoPilot AI live demo →](https://repopilot-ai-ukctftlq66yjsk8bafzmwy.streamlit.app/)**

---

## ✨ What RepoPilot does

RepoPilot turns the first pass through an unfamiliar repository into a focused workflow:

1. **Paste** a GitHub repository URL.
2. **Map** metadata, languages, files, architecture, activity, and project signals.
3. **Explore** source files in the browser with a searchable code explorer.
4. **Review** explainable quality insights instead of opaque scores.
5. **Ask** repository-aware questions with optional AI assistance.
6. **Export** a Markdown report for a handoff, review, or project record.

Core repository analysis works without an AI provider key.

---

## 🎯 Product highlights

| Area | Included |
| --- | --- |
| **Repository overview** | Stars, forks, default branch, update date, file counts, primary language, and quality score. |
| **Architecture map** | Detected stacks, entry points, layers, documentation files, test files, and CI workflows. |
| **Language breakdown** | GitHub language composition with visual percentage bars. |
| **Code Explorer** | Searchable repository tree, source previews, line numbers, and file metadata. |
| **Quality Insights** | Lightweight, explainable static signals grouped by high, medium, and low priority. |
| **Ask RepoPilot** | Context-aware questions about the repository, architecture, stack, or selected files. |
| **AI explanations** | Optional OpenAI-compatible or Anthropic-backed explanations through the API. |
| **Report export** | Download a Markdown summary containing repository context, architecture, languages, quality insights, and activity. |
| **Recent scans** | Keep the latest repository history in the browser’s local storage. |
| **Safe defaults** | Read-only GitHub inspection; repository code is not checked out or executed. |

---

## 🖥️ Screens and workflow

### Welcome workspace

Start with one clean repository URL field, quick-start examples, and a clear explanation of what RepoPilot can inspect without credentials.

### Repository overview

See the repository’s most important signals at a glance: language composition, architecture summary, file structure, quality score, recent signals, and recent commits.

### Code Explorer

Filter the indexed tree, open a source file, inspect its content with line numbers, and request an explanation for the active file when an AI provider is configured.

### Quality Insights

Review static signals by severity. Every signal is presented as a review prompt — not as a claim of perfect correctness or a full security audit.

### Ask RepoPilot

Ask questions using the repository map and, optionally, the currently selected source file as context. Without an external provider, the app still returns local fallback guidance.

---

## 🧱 Architecture

```text
┌──────────────────────────────┐
│ React 19 + Vite dashboard     │
│ frontend/src/App.jsx         │
└──────────────┬───────────────┘
               │ JSON over HTTP
               ▼
┌──────────────────────────────┐
│ FastAPI service               │
│ backend/app/main.py          │
│                              │
│  /api/health                 │
│  /api/analyze                │
│  /api/file                   │
│  /api/explain                │
│  /api/ask                   │
└──────────────┬───────────────┘
               │
      ┌────────┴─────────┐
      ▼                  ▼
 GitHub REST API     Optional LLM provider
```

### Backend responsibilities

- Validate and normalize GitHub repository URLs.
- Read repository metadata, language statistics, trees, files, and commits.
- Run bounded, explainable static quality checks.
- Cache analyses briefly to reduce repeated GitHub requests.
- Keep GitHub and AI credentials on the backend.
- Provide local fallback answers when no AI provider is configured.

### Frontend responsibilities

- Render the repository workspace and navigation.
- Display analysis, architecture, activity, and quality signals.
- Fetch individual files on demand.
- Maintain recent scan history in browser `localStorage`.
- Export the current analysis as Markdown.

---

## 🛡️ Safety and privacy boundaries

RepoPilot is designed for inspection, not execution:

- Repository code is read through GitHub APIs; it is not cloned or run.
- GitHub and LLM keys are read by the FastAPI backend only.
- The browser receives analysis results and requested source content, not provider secrets.
- Quality signals are conservative prompts for review, not proof of security or correctness.
- The default deployment uses `LLM_PROVIDER=none`, so basic analysis does not require an AI key.
- Public internet deployments should add authentication, quotas, and rate limiting before exposing private integrations.

---

## 🧰 Stack

### Frontend

- React 19
- Vite 7
- Lucide React icons
- CSS custom design system

### Backend

- Python 3.14
- FastAPI
- Uvicorn
- HTTPX
- python-dotenv

### Integrations

- GitHub REST API
- OpenAI-compatible providers
- Anthropic
- Any OpenAI-compatible endpoint through `OPENAI_BASE_URL`

### Deployment

- Optional single-image Docker deployment via `Dockerfile`

---

## 🚀 Quick start

### Requirements

- Python 3.10+ recommended; the project’s deployment configuration targets Python 3.14.
- Node.js and npm for the Vite frontend.
- Internet access to GitHub for live repository analysis.

### 1. Clone the project

```bash
git clone https://github.com/mehulikhanra904-prog/REPOPILOT-AI.git
cd REPOPILOT-AI
```

### 2. Create and activate a Python environment

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

### 3. Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For a fully pinned environment, use `requirements.lock` instead.

### 4. Start the API

```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

Check that it is running:

```text
http://localhost:8000/api/health
```

### 5. Start the frontend

Open a second terminal in the repository root:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open:

```text
http://localhost:5173
```

The Vite development proxy forwards `/api` requests to `http://127.0.0.1:8000`.

---

## 🔐 Environment configuration

Create a local `.env` file from `.env.example` and keep it out of version control:

```dotenv
GITHUB_TOKEN=
LLM_PROVIDER=none
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-latest
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
API_TIMEOUT_SECONDS=20
ANALYSIS_CACHE_TTL_SECONDS=300
ANALYSIS_CACHE_MAX_ENTRIES=32
```

### GitHub token

`GITHUB_TOKEN` raises GitHub API limits and can allow access to repositories available to that token. Only the backend reads it.

### OpenAI-compatible provider

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

You can point `OPENAI_BASE_URL` at another compatible provider.

### Anthropic

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key
ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

Never commit API keys, tokens, `.env`, or generated credentials.

---

## 📡 API surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | API and active AI provider health. |
| `POST` | `/api/analyze` | Repository metadata, language composition, tree, activity, architecture, and quality signals. |
| `POST` | `/api/file` | Fetch a selected source file from the repository. |
| `POST` | `/api/explain` | Explain a selected file with the configured provider or local fallback. |
| `POST` | `/api/ask` | Ask a repository-aware question with optional selected-file context. |

Example analysis request:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/fastapi/fastapi"}'
```

---

## 🧪 Test and build

Run backend tests from the repository root:

```bash
python -m pytest backend/tests -q
```

Build the frontend:

```bash
npm --prefix frontend run build
```

Preview the production frontend locally:

```bash
npm --prefix frontend run preview
```

---

## 🗂️ Project structure

```text
REPOPILOT-AI/
├── backend/
│   ├── app/
│   │   ├── config.py       # Environment-backed settings
│   │   ├── github.py       # GitHub API access and repository analysis
│   │   ├── llm.py          # Provider adapters and local fallbacks
│   │   ├── main.py         # FastAPI routes and cache
│   │   └── models.py       # Request models
│   └── tests/              # Offline backend tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Dashboard and interaction flow
│   │   ├── main.jsx        # React entry point
│   │   └── styles.css      # Visual system and responsive layout
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .env.example
├── Dockerfile
├── requirements.txt
├── requirements.lock
└── README.md
```

---

## ⚠️ Product notes and limitations

The static quality pass is intentionally explainable and conservative. It looks for signals such as unfinished TODO markers, dynamic execution, broad error handling, debug output, very large modules, missing README files, and an obvious lack of tests.

It is **not**:

- A full security audit
- A dependency vulnerability database
- A proof that a repository is safe or production-ready
- A replacement for the project’s own tests, linting, type checks, or security tooling

Before exposing a deployment with GitHub or LLM credentials, add production authentication, request quotas, rate limiting, audit logging, and a deliberate secrets-management strategy.

---

## 🗺️ Roadmap ideas

- Pull-request and commit comparison reports
- Configurable quality profiles by language and project type
- More framework and dependency signals
- Provider health and latency metrics
- Team workspaces and persisted scan history
- CI checks for repository health regressions

---

## 📄 License

No license has been declared for this project yet. Add a `LICENSE` file before distributing or reusing the code under specific terms.

---

<p align="center">
  <strong>RepoPilot AI</strong><br />
  <em>See the repository clearly. Fix the right things first.</em>
</p>
