# RepoPilot AI

RepoPilot AI is a portfolio-quality GitHub repository analyzer. Paste a public
GitHub URL to get an interactive repository map with metadata, language
composition, file exploration, explainable static quality signals, and a
context-aware question panel.

The MVP is intentionally useful without credentials: GitHub metadata, the file
tree, source browsing, and the local static scan work in `LLM_PROVIDER=none`
mode. Optional OpenAI-compatible or Anthropic providers can add generated code
explanations and answers, while their keys remain on the FastAPI backend.

## Stack

- **Frontend:** React 19 + Vite 7 + Lucide icons
- **Backend:** Python 3.14 + FastAPI + httpx
- **Data:** GitHub REST API (no GitHub SDK or browser token required)
- **AI:** provider-neutral HTTP adapters for OpenAI-compatible APIs and Anthropic
- **Deployment:** one Docker image can serve the built dashboard and API

## Run locally on Windows PowerShell

Open PowerShell in this repository directory:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm --prefix frontend install
```

`requirements.txt` keeps the human-maintained direct dependency contract;
`requirements.lock` pins the complete Python environment used by the Docker
image and the verified local setup. `frontend/package-lock.json` does the same
for the Vite app.

Start the backend in PowerShell window 1:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Start the Vite dashboard in PowerShell window 2:

```powershell
npm --prefix frontend run dev
```

Open <http://localhost:5173>. The Vite development proxy forwards `/api`
requests to FastAPI at `http://127.0.0.1:8000`.

### Optional credentials

Edit `.env` (never commit it):

- `GITHUB_TOKEN` raises GitHub API limits and allows access to repositories the
  token can read.
- Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY`, or
  `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`, to enable generated answers.
- You can point `OPENAI_BASE_URL` at any OpenAI-compatible provider. Keys are
  read only by FastAPI and are never included in frontend JavaScript.

This MVP is designed for local/trusted use. Before exposing a deployment to
the public internet with `GITHUB_TOKEN` or an LLM key, add user authentication,
request quotas, and rate limiting around the API endpoints.

## Test and build

Run the backend tests offline from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest backend/tests -q
```

Build the frontend:

```powershell
npm --prefix frontend run build
```

Run the production-shaped container (Docker Desktop):

```powershell
docker build -t repilot-ai .
docker run --rm -p 8000:8000 --env-file .env repilot-ai
```

Then open <http://localhost:8000>. The Docker image contains the Vite build and
FastAPI serves it as a single application. The container does not require an
LLM key for basic repository analysis.

## Deploy to Render without Docker

The repository includes `render.yaml` for a native Render deployment. It
creates a Python web service for FastAPI and a Render static site for the Vite
dashboard.

1. Push this repository to a GitHub repository.
2. In Render, choose **New → Blueprint**, connect the GitHub repository, and
   select the branch containing `render.yaml`.
3. Review the two services (`repilot-api` and `repilot-ui`) and click **Apply**.
4. In the `repilot-api` environment settings, add `GITHUB_TOKEN` if you need
   higher GitHub limits or private repository access. Add an LLM provider key
   only when you want generated explanations.
5. If you rename either Render service, update `ALLOWED_ORIGINS` on the API
   and `VITE_API_URL` on the static site to the actual Render URLs, then
   redeploy the static site.

The default Blueprint keeps `LLM_PROVIDER=none`, so the deployed app still
supports repository analysis, file browsing, static quality signals, report
export, and local fallback questions without AI credentials.

## API surface

- `GET /api/health` — backend and provider mode health
- `POST /api/analyze` — metadata, languages, tree, and static quality signals
- `POST /api/file` — fetch a source file from the selected repository
- `POST /api/explain` — explain a file with the configured provider or local fallback
- `POST /api/ask` — ask a repository-aware question with the configured provider or local fallback

## Product notes

The static quality pass is intentionally explainable and conservative. It
looks for signals such as unfinished TODO markers, dynamic execution, broad
error handling, debug output, very large modules, missing README files, and an
obvious lack of tests. It is not a security audit and should be paired with
the repository's own test, lint, and security tooling.
