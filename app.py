"""RepoPilot - Streamlit frontend for the local repository analyzer."""

from __future__ import annotations

import inspect
import json
import hashlib
import hmac
from html import escape
import re
import secrets
from pathlib import Path
from typing import Any

import streamlit as st

try:
    import analyzer  # type: ignore
except ImportError as exc:  # pragma: no cover - shown in the UI
    analyzer = None
    ANALYZER_IMPORT_ERROR = exc
else:
    ANALYZER_IMPORT_ERROR = None


ROOT = Path(__file__).parent
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@st.cache_resource(show_spinner=False)
def get_auth_users() -> dict[str, dict[str, str]]:
    """Return the process-local demo account store shared by Streamlit sessions."""
    return {}


def inject_styles() -> None:
    css_path = ROOT / "styles.css"
    if css_path.exists():
        st.html(f"<style>{css_path.read_text(encoding='utf-8')}</style>")


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return a salted password hash for the local demo account store."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex(), digest.hex()


def passwords_match(password: str, stored: dict[str, str]) -> bool:
    _, candidate = hash_password(password, bytes.fromhex(stored["salt"]))
    return hmac.compare_digest(candidate, stored["hash"])


def render_auth() -> bool:
    """Render the local-only demo auth gate and return whether it is unlocked."""
    if st.session_state.get("auth_user"):
        return True

    auth_users = get_auth_users()

    left, center, right = st.columns([1, 1.4, 1])
    with center:
        st.markdown('<div class="auth-mark">RP</div>', unsafe_allow_html=True)
        st.markdown('<div class="eyebrow auth-eyebrow">REPOPILOT / LOCAL DEMO</div>', unsafe_allow_html=True)
        st.title("Repository clarity, on demand.", anchor=False)
        st.markdown('<p class="auth-lede">Sign in to your local RepoPilot workspace and keep your analysis history in this browser session.</p>', unsafe_allow_html=True)
        st.caption(":material/lock: Local demo auth · accounts and sessions are cleared when the app session ends")

        mode = st.radio("Auth mode", ["Sign in", "Create account"], horizontal=True, label_visibility="collapsed", key="auth_mode")
        with st.container(border=True):
            if mode == "Sign in":
                with st.form("sign_in_form", clear_on_submit=False):
                    email = st.text_input("Email", placeholder="you@example.com", key="sign_in_email")
                    show_password = st.checkbox("Show password", key="sign_in_show_password")
                    password = st.text_input("Password", type="default" if show_password else "password")
                    submitted = st.form_submit_button("Sign in", type="primary", width="stretch", icon=":material/login:")
                if submitted:
                    account = auth_users.get(email.strip().lower())
                    if account and passwords_match(password, account):
                        st.session_state.auth_user = email.strip().lower()
                        st.rerun()
                    st.error("We couldn't sign you in. Check your email and password, then try again.")
            else:
                with st.form("create_account_form", clear_on_submit=False):
                    email = st.text_input("Email", placeholder="you@example.com", key="sign_up_email")
                    show_password = st.checkbox("Show password", key="sign_up_show_password")
                    password = st.text_input("Password", type="default" if show_password else "password")
                    confirm = st.text_input("Confirm password", type="default" if show_password else "password")
                    submitted = st.form_submit_button("Create account", type="primary", width="stretch", icon=":material/person_add:")
                if submitted:
                    normalized_email = email.strip().lower()
                    if not EMAIL_PATTERN.match(normalized_email):
                        st.error("Enter a valid email address.")
                    elif len(password) < 8:
                        st.error("Use at least 8 characters for the password.")
                    elif password != confirm:
                        st.error("Passwords do not match.")
                    elif normalized_email in auth_users:
                        st.error("An account with that email already exists. Use Sign in instead.")
                    else:
                        salt, digest = hash_password(password)
                        auth_users[normalized_email] = {"salt": salt, "hash": digest}
                        st.session_state.auth_user = normalized_email
                        st.rerun()
        st.caption("Demo accounts are available while this app process is running. Passwords are hashed and never stored in plaintext.")
    return False


def get_value(data: Any, *keys: str, default: Any = None) -> Any:
    """Read a value from either a dict or an analyzer result object."""
    for key in keys:
        if isinstance(data, dict) and key in data:
            return data[key]
        if hasattr(data, key):
            return getattr(data, key)
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def run_analyzer(repo_url: str, status: Any) -> Any:
    """Call the analyzer without assuming one particular public API."""
    if analyzer is None:
        raise RuntimeError(
            "The analyzer module could not be imported. Add analyzer.py to this folder "
            "and install its dependencies before analyzing a repository."
        ) from ANALYZER_IMPORT_ERROR

    candidates = [
        getattr(analyzer, name, None)
        for name in ("analyze_repository", "analyze", "run_analysis", "run")
    ]
    function = next((item for item in candidates if callable(item)), None)
    if function is None:
        raise RuntimeError(
            "analyzer.py does not expose analyze_repository(), analyze(), run_analysis(), or run()."
        )

    def progress(phase: str, *_args: Any, **_kwargs: Any) -> None:
        status.update(label=f"Running · {phase}")

    kwargs: dict[str, Any] = {}
    try:
        parameters = inspect.signature(function).parameters
        for name in ("repo_url", "repository_url", "url", "repo"):
            if name in parameters:
                kwargs[name] = repo_url
                break
        for name in ("progress_callback", "progress", "on_progress"):
            if name in parameters:
                kwargs[name] = progress
                break
        if not kwargs:
            result = function(repo_url)
        else:
            result = function(**kwargs)
    except (TypeError, ValueError):
        result = function(repo_url)
    return result


def score_color(score: Any) -> str:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return "neutral"
    return "good" if numeric >= 80 else "warn" if numeric >= 60 else "bad"


def finding_text(finding: Any, key: str, default: str = "") -> str:
    value = get_value(finding, key, default=default)
    return str(value) if value is not None else default


def make_report(result: Any, repo_url: str) -> str:
    supplied = get_value(result, "markdown", "report_markdown", "report")
    if isinstance(supplied, str) and supplied.strip():
        return supplied
    exporter = getattr(analyzer, "to_markdown", None) if analyzer is not None else None
    if callable(exporter):
        exported = exporter(result)
        if isinstance(exported, str) and exported.strip():
            return exported
    overview = get_value(result, "overview", "metadata", default={})
    findings = as_list(get_value(result, "findings", "issues", "recommendations"))
    lines = ["# RepoPilot repository report", "", f"Repository: {repo_url}", ""]
    lines += ["## Overview", "", json.dumps(overview, indent=2, default=str), "", "## Findings", ""]
    for finding in findings:
        lines.append(f"- **{finding_text(finding, 'title', 'Finding')}** — {finding_text(finding, 'description', finding_text(finding, 'message'))}")
    return "\n".join(lines) + "\n"


def render_landing() -> None:
    st.markdown('<div class="eyebrow">REPOPILOT / REPOSITORY INTELLIGENCE</div>', unsafe_allow_html=True)
    st.title("Understand your repository\nbefore you change it.", anchor=False)
    st.markdown("Paste a public GitHub URL and get an evidence-backed map of health, risk, and the best first fixes.")
    st.space("small")
    with st.form("analyze_form", clear_on_submit=False):
        url = st.text_input("GitHub repository URL", placeholder="https://github.com/org/repository", label_visibility="collapsed")
        submitted = st.form_submit_button("Analyze repository  →", type="primary", width="stretch")
    if submitted:
        if not url.strip():
            st.error("Enter a GitHub repository URL to begin.")
            return
        st.session_state.repo_url = url.strip()
        st.session_state.result = None
        with st.status("Preparing analysis", expanded=True) as status:
            try:
                status.write("Validating repository input")
                result = run_analyzer(st.session_state.repo_url, status)
                st.session_state.result = result
                status.update(label="Analysis complete", state="complete", expanded=False)
            except Exception as exc:  # analyzer errors belong in the app, not a traceback
                status.update(label="Analysis failed", state="error", expanded=True)
                st.error(f"{type(exc).__name__}: {exc}")
                st.caption("Check the repository URL and the analyzer installation, then try again.")
                return
        st.rerun()


def render_dashboard(result: Any, repo_url: str) -> None:
    st.markdown('<div class="eyebrow">ANALYSIS COMPLETE</div>', unsafe_allow_html=True)
    st.title("Repository overview", anchor=False)
    st.markdown(f'<div class="repo-pill">:material/code: {repo_url}</div>', unsafe_allow_html=True)

    overview = get_value(result, "overview", "metadata", default={})
    scores = get_value(result, "health_scores", "scores", "health", default={})
    if isinstance(scores, dict) and "score" in scores:
        scores = {"Overall health": scores["score"]}
    if not isinstance(scores, dict):
        scores = {"Overall health": scores}
    findings = as_list(get_value(result, "findings", "issues", "recommendations"))
    phases = as_list(get_value(result, "phases", "completed_phases", "steps"))
    if not phases:
        phases = [name for name in ("metadata", "tree", "files", "findings", "health") if get_value(result, name) is not None]

    languages = get_value(result, "languages", default={})
    primary_language = next(iter(languages), "—") if isinstance(languages, dict) and languages else "—"

    with st.container(border=True):
        st.subheader("Analysis status", anchor=False)
        cols = st.columns(max(1, min(4, len(phases) or 1)))
        if phases:
            for col, phase in zip(cols, phases):
                label = phase if isinstance(phase, str) else get_value(phase, "name", "label", default="Phase")
                complete = phase if isinstance(phase, str) else get_value(phase, "completed", "status", default=True)
                with col:
                    st.markdown(f":material/{'check_circle' if complete else 'radio_button_unchecked'}: **{label}**")
        else:
            st.caption("The analyzer returned no phase metadata. Results below reflect the completed analyzer response.")
            st.badge("Complete", icon=":material/check_circle:", color="green")

    info_cols = st.columns(4)
    overview_items = [
        ("Language", get_value(overview, "language", "primary_language", default=primary_language)),
        ("Files analyzed", get_value(overview, "files", "file_count", default=get_value(get_value(result, "limits", default={}), "files_seen", default="—"))),
        ("Open findings", len(findings)),
        ("Default branch", get_value(overview, "default_branch", "branch", default="—")),
    ]
    for col, (label, value) in zip(info_cols, overview_items):
        with col:
            st.metric(label, value, border=True)

    st.subheader("Health signals", anchor=False)
    score_cols = st.columns(min(4, max(1, len(scores))))
    for col, (label, score) in zip(score_cols, scores.items()):
        with col:
            with st.container(border=True):
                st.markdown(f'<div class="score-label">{label}</div><div class="score {score_color(score)}">{score}<span>/100</span></div>', unsafe_allow_html=True)
                with st.expander("How this score is calculated", icon=":material/insights:"):
                    methodology = get_value(result, "methodology", "score_methodology", default={})
                    explanation = get_value(methodology, str(label), default="The analyzer did not provide a methodology for this signal.")
                    st.caption(str(explanation))

    st.subheader("Fix first", anchor=False)
    if not findings:
        st.success("No findings were returned by the analyzer.", icon=":material/check_circle:")
    for index, finding in enumerate(findings, 1):
        title = finding_text(finding, "title", finding_text(finding, "name", f"Finding {index}"))
        severity = finding_text(finding, "severity", finding_text(finding, "confidence", "review"))
        with st.container(border=True):
            top = st.columns([5, 1])
            with top[0]:
                st.markdown(f"**{index:02d}  {title}**")
                st.caption(finding_text(finding, "description", finding_text(finding, "message", "No description provided.")))
            with top[1]:
                st.badge(severity.capitalize(), color="red" if severity.lower() in {"critical", "high"} else "orange")
            with st.expander("View evidence", icon=":material/receipt_long:"):
                evidence = get_value(finding, "evidence", "details", "proof", default=None)
                if evidence is None:
                    st.caption("No evidence details were returned for this finding.")
                elif isinstance(evidence, (dict, list)):
                    st.json(evidence)
                else:
                    st.code(str(evidence), language="text")
                location = get_value(finding, "file", "path", "location")
                if location:
                    st.caption(f"Location: `{location}`")

    st.subheader("Architecture and tree", anchor=False)
    tree = get_value(result, "tree", "file_tree", "architecture", default=None)
    if tree is None:
        tree = [get_value(item, "path", default=item) for item in as_list(get_value(result, "files", default=[]))]
    if tree is None:
        st.caption("The analyzer did not return a repository tree.")
    elif isinstance(tree, str):
        st.code(tree, language="text")
    else:
        st.json(tree, expanded=False)

    report = make_report(result, repo_url)
    st.download_button("Download markdown report", report, file_name="repopilot-report.md", mime="text/markdown", icon=":material/download:", type="secondary")


st.set_page_config(page_title="RepoPilot", page_icon=":material/terminal:", layout="wide", initial_sidebar_state="collapsed")
inject_styles()

if "result" not in st.session_state:
    st.session_state.result = None
if "repo_url" not in st.session_state:
    st.session_state.repo_url = ""
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if not render_auth():
    st.stop()

with st.sidebar:
    st.markdown("## :material/terminal: RepoPilot")
    st.caption("Repository intelligence for developers")
    safe_user = escape(str(st.session_state.auth_user))
    st.markdown(f'<div class="sidebar-user"><span class="sidebar-user-label">Signed in as</span><strong>{safe_user}</strong></div>', unsafe_allow_html=True)
    if st.session_state.result is not None and st.button("New analysis", icon=":material/add:", width="stretch"):
        st.session_state.result = None
        st.session_state.repo_url = ""
        st.rerun()
    if st.button("Log out", icon=":material/logout:", width="stretch"):
        st.session_state.auth_user = None
        st.session_state.result = None
        st.session_state.repo_url = ""
        st.rerun()
    st.caption("Analyzer-backed · evidence first")

if st.session_state.result is None:
    render_landing()
else:
    render_dashboard(st.session_state.result, st.session_state.repo_url)
