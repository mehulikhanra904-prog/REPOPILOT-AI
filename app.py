"""RepoPilot - evidence-first repository intelligence for a local demo."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import re
import secrets
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

try:
    import analyzer  # type: ignore
except ImportError as exc:  # pragma: no cover - surfaced in the UI
    analyzer = None
    ANALYZER_IMPORT_ERROR = exc
else:
    ANALYZER_IMPORT_ERROR = None


ROOT = Path(__file__).parent
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def inject_styles() -> None:
    css_path = ROOT / "styles.css"
    if css_path.exists():
        st.html(f"<style>{css_path.read_text(encoding='utf-8')}</style>")


def init_state() -> None:
    """Keep per-browser demo state in one explicit place."""
    defaults = {
        "result": None,
        "repo_url": "",
        "history": [],
        "auth_users": {},
        "auth_user": None,
        "active_view": "Analyze",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


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

    left, center, right = st.columns([1, 1.15, 1])
    with center:
        st.markdown('<div class="auth-mark"><span>RP</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="eyebrow auth-eyebrow">REPOPILOT / LOCAL DEMO</div>', unsafe_allow_html=True)
        st.title("Repository clarity, on demand.", anchor=False)
        st.markdown(
            '<p class="auth-lede">A focused workspace for turning a public GitHub repository into a readable, evidence-backed review.</p>',
            unsafe_allow_html=True,
        )
        st.caption(":material/lock: Local demo auth · sessions and accounts stay in this browser session")

        mode = st.radio(
            "Auth mode",
            ["Sign in", "Create account"],
            horizontal=True,
            label_visibility="collapsed",
            key="auth_mode",
        )
        with st.container(border=True):
            if mode == "Sign in":
                with st.form("sign_in_form", clear_on_submit=False):
                    email = st.text_input("Email", placeholder="you@example.com", key="sign_in_email")
                    show_password = st.checkbox("Show password", key="sign_in_show_password")
                    password = st.text_input("Password", type="default" if show_password else "password")
                    submitted = st.form_submit_button(
                        "Sign in", type="primary", width="stretch", icon=":material/login:"
                    )
                if submitted:
                    account = st.session_state.auth_users.get(email.strip().lower())
                    if account and passwords_match(password, account):
                        st.session_state.auth_user = email.strip().lower()
                        st.rerun()
                    st.error("That email and password combination was not found in this session.")
            else:
                with st.form("create_account_form", clear_on_submit=False):
                    email = st.text_input("Email", placeholder="you@example.com", key="sign_up_email")
                    show_password = st.checkbox("Show password", key="sign_up_show_password")
                    password = st.text_input("Password", type="default" if show_password else "password")
                    confirm = st.text_input(
                        "Confirm password", type="default" if show_password else "password"
                    )
                    submitted = st.form_submit_button(
                        "Create account", type="primary", width="stretch", icon=":material/person_add:"
                    )
                if submitted:
                    normalized_email = email.strip().lower()
                    if not EMAIL_PATTERN.match(normalized_email):
                        st.error("Enter a valid email address.")
                    elif len(password) < 8:
                        st.error("Use at least 8 characters for the password.")
                    elif password != confirm:
                        st.error("Passwords do not match.")
                    elif normalized_email in st.session_state.auth_users:
                        st.error("An account with that email already exists in this session.")
                    else:
                        salt, digest = hash_password(password)
                        st.session_state.auth_users[normalized_email] = {"salt": salt, "hash": digest}
                        st.session_state.auth_user = normalized_email
                        st.rerun()
        st.caption("Demo only: no account data is persisted, and this is not production security.")
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
        result = function(repo_url) if not kwargs else function(**kwargs)
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


def repo_name(result: Any, repo_url: str) -> str:
    metadata = get_value(result, "metadata", "overview", default={})
    name = get_value(metadata, "full_name", "name", default="")
    if name:
        return str(name)
    return repo_url.rstrip("/").split("/")[-1] or "Repository"


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
        lines.append(
            f"- **{finding_text(finding, 'title', 'Finding')}** — "
            f"{finding_text(finding, 'description', finding_text(finding, 'message'))}"
        )
    return "\n".join(lines) + "\n"


def add_history(result: Any, repo_url: str) -> None:
    history = st.session_state.history
    history.insert(
        0,
        {
            "repo_url": repo_url,
            "name": repo_name(result, repo_url),
            "analyzed_at": datetime.now().strftime("%b %d, %Y · %H:%M"),
            "result": result,
        },
    )
    st.session_state.history = history[:8]


def reset_analysis() -> None:
    st.session_state.result = None
    st.session_state.repo_url = ""
    st.session_state.active_view = "Analyze"


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div class="brand-lockup"><div class="brand-glyph">RP</div><div><strong>RepoPilot</strong><span>repository intelligence</span></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-rule"></div>', unsafe_allow_html=True)
        st.caption("WORKSPACE")
        options = ["Analyze", "History", "Methodology"]
        st.session_state.workspace_nav = st.session_state.active_view
        active = st.radio(
            "Workspace navigation",
            options,
            index=options.index(st.session_state.active_view),
            label_visibility="collapsed",
            key="workspace_nav",
        )
        st.session_state.active_view = active

        st.markdown('<div class="sidebar-status"><span class="status-dot"></span><div><strong>Local demo ready</strong><small>Read-only GitHub inspection</small></div></div>', unsafe_allow_html=True)
        if st.session_state.result is not None:
            current_name = escape(repo_name(st.session_state.result, st.session_state.repo_url))
            st.markdown(
                f'<div class="sidebar-current"><span>ACTIVE REVIEW</span><strong>{current_name}</strong><small>{escape(st.session_state.repo_url)}</small></div>',
                unsafe_allow_html=True,
            )
        st.space("small")
        if st.button("New analysis", icon=":material/add:", width="stretch"):
            reset_analysis()
            st.rerun()
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            st.session_state.auth_user = None
            reset_analysis()
            st.rerun()
        st.markdown('<div class="sidebar-footer">Analyzer-backed · evidence first<br>Session history is local to this tab</div>', unsafe_allow_html=True)


def render_landing() -> None:
    st.markdown('<div class="hero-orb orb-one"></div><div class="hero-orb orb-two"></div>', unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">REPOPILOT / REPOSITORY INTELLIGENCE</div>', unsafe_allow_html=True)
    st.title("See the shape of a repository\nbefore you change it.", anchor=False)
    st.markdown(
        '<p class="hero-lede">RepoPilot turns a public GitHub repository into a compact, evidence-backed review of its structure, health signals, and highest-priority findings.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-chips"><span>:material/visibility: read-only inspection</span><span>:material/verified_user: evidence-linked findings</span><span>:material/history: session history</span></div>',
        unsafe_allow_html=True,
    )
    with st.form("analyze_form", clear_on_submit=False, border=False):
        st.markdown('<div class="input-label">START WITH A PUBLIC REPOSITORY</div>', unsafe_allow_html=True)
        url = st.text_input(
            "GitHub repository URL",
            placeholder="https://github.com/org/repository",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Analyze repository", type="primary", width="stretch", icon=":material/arrow_forward:"
        )
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
                add_history(result, st.session_state.repo_url)
                status.update(label="Analysis complete", state="complete", expanded=False)
            except Exception as exc:  # analyzer errors belong in the app, not a traceback
                status.update(label="Analysis failed", state="error", expanded=True)
                st.error(f"{type(exc).__name__}: {exc}")
                st.caption("Check the repository URL and the analyzer installation, then try again.")
                return
        st.rerun()

    st.space("large")
    st.markdown('<div class="landing-section-label">A review surface designed for fast decisions</div>', unsafe_allow_html=True)
    feature_cols = st.columns(3)
    features = [
        ("01", "Map the repository", "See languages, frameworks, files, and the bounded architecture returned by the analyzer."),
        ("02", "Prioritize what matters", "Findings are grouped by real analyzer severity and category, with no invented scores."),
        ("03", "Show the proof", "Open each finding to inspect the exact evidence, location, and analyzer limitation."),
    ]
    for col, (number, title, description) in zip(feature_cols, features):
        with col:
            st.markdown(
                f'<div class="feature-card"><span class="feature-number">{number}</span><strong>{title}</strong><p>{description}</p></div>',
                unsafe_allow_html=True,
            )


def normalize_scores(result: Any) -> dict[str, Any]:
    scores = get_value(result, "health_scores", "scores", "health", default={})
    if isinstance(scores, dict) and "score" in scores:
        return {"Overall health": scores}
    if not isinstance(scores, dict):
        return {"Overall health": scores}
    return scores


def primary_language(result: Any) -> str:
    """Return a display-safe primary language from any analyzer response shape."""
    languages = get_value(result, "languages", default={})
    if isinstance(languages, dict):
        return str(next(iter(languages), "—"))
    if isinstance(languages, (list, tuple)):
        return str(languages[0]) if languages else "—"
    return str(languages) if languages else "—"


def finding_category(finding: Any) -> str:
    return finding_text(finding, "type", finding_text(finding, "category", "Other")).replace("_", " ").title()


def finding_severity(finding: Any) -> str:
    return finding_text(finding, "severity", finding_text(finding, "confidence", "review")).lower()


def severity_color(severity: str) -> str:
    return {"critical": "red", "high": "red", "medium": "orange", "low": "blue"}.get(severity, "gray")


def render_executive_summary(result: Any, repo_url: str, findings: list[Any], scores: dict[str, Any]) -> None:
    metadata = get_value(result, "metadata", "overview", default={})
    languages = get_value(result, "languages", default={})
    frameworks = as_list(get_value(result, "frameworks", default=[]))
    health = get_value(result, "health", "health_scores", "scores", default={})
    overall = get_value(health, "score", default=None)
    summary_parts = []
    if overall is not None:
        summary_parts.append(f"The analyzer returned an overall health signal of **{overall}/{get_value(health, 'max', default=100)}**.")
    summary_parts.append(f"It inspected **{get_value(get_value(result, 'limits', default={}), 'files_seen', default='the available')}** files from this repository.")
    if findings:
        summary_parts.append(f"There are **{len(findings)} analyzer findings** to review, ordered for evidence-first triage.")
    else:
        summary_parts.append("The analyzer returned no findings for the bounded inspection.")
    st.markdown('<div class="section-kicker">EXECUTIVE SUMMARY</div>', unsafe_allow_html=True)
    with st.container(border=True):
        left, right = st.columns([1.65, 1], vertical_alignment="center")
        with left:
            st.markdown("### A fast read on this repository")
            st.markdown(" ".join(summary_parts))
            st.caption(
                f"{get_value(metadata, 'description', default='No repository description returned.') or 'No repository description returned.'}"
            )
        with right:
            summary_items = []
            if languages:
                top_language = next(iter(languages)) if isinstance(languages, dict) else str(languages)
                summary_items.append(("Primary language", top_language))
            if frameworks:
                summary_items.append(("Detected frameworks", ", ".join(map(str, frameworks))))
            summary_items.append(("Repository", repo_name(result, repo_url)))
            for label, value in summary_items:
                st.markdown(f'<div class="summary-row"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>', unsafe_allow_html=True)


def render_health(result: Any, scores: dict[str, Any]) -> None:
    st.markdown('<div class="section-kicker">HEALTH SIGNALS</div>', unsafe_allow_html=True)
    score_items = list(scores.items())
    if not score_items:
        st.caption("The analyzer did not return health signals.")
        return
    score_cols = st.columns(min(4, max(1, len(score_items))))
    methodology = get_value(result, "methodology", "score_methodology", default={})
    for col, (label, score_data) in zip(score_cols, score_items):
        with col:
            numeric = get_value(score_data, "score", default=score_data)
            maximum = get_value(score_data, "max", default=100)
            with st.container(border=True):
                st.markdown(f'<div class="score-label">{escape(str(label))}</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="score {score_color(numeric)}">{escape(str(numeric))}<span>/{escape(str(maximum))}</span></div>',
                    unsafe_allow_html=True,
                )
                explanation = get_value(methodology, str(label), default=None)
                if explanation:
                    with st.expander("Score methodology", icon=":material/insights:"):
                        st.caption(str(explanation))


def render_finding(finding: Any, index: int) -> None:
    title = finding_text(finding, "title", finding_text(finding, "name", f"Finding {index}"))
    severity = finding_severity(finding)
    category = finding_category(finding)
    description = finding_text(
        finding,
        "description",
        finding_text(finding, "message", "The analyzer did not return a description."),
    )
    path = get_value(finding, "path", "file", "location", default="")
    line = get_value(finding, "line", "line_number", default=None)
    location = f"{path}:{line}" if path and line else str(path) if path else "Repository-level signal"
    with st.container(border=True):
        top = st.columns([0.12, 4.8, 1.15], vertical_alignment="top")
        with top[0]:
            st.markdown(f'<div class="finding-index">{index:02d}</div>', unsafe_allow_html=True)
        with top[1]:
            st.markdown(f"### {escape(title)}")
            st.markdown(f"<p class=\"finding-description\">{escape(description)}</p>", unsafe_allow_html=True)
            st.caption(f":material/{'location_on' if path else 'hub'}: `{escape(location)}` · {category}")
        with top[2]:
            st.badge(severity.capitalize(), color=severity_color(severity))
        with st.expander("Inspect evidence", icon=":material/receipt_long:"):
            evidence = get_value(finding, "evidence", "details", "proof", default=None)
            if evidence is None:
                st.caption("No evidence details were returned for this finding.")
            elif isinstance(evidence, (dict, list)):
                st.json(evidence)
            else:
                st.code(str(evidence), language="text")
            limitation = get_value(finding, "limitation", default=None)
            if limitation:
                st.caption(f":material/info: {limitation}")


def render_findings(result: Any, findings: list[Any]) -> None:
    st.markdown('<div class="section-kicker">FINDINGS / EVIDENCE</div>', unsafe_allow_html=True)
    if not findings:
        st.success("No findings were returned by the analyzer.", icon=":material/check_circle:")
        return

    severities = sorted({finding_severity(item).capitalize() for item in findings})
    categories = sorted({finding_category(item) for item in findings})
    filter_cols = st.columns([1, 1, 1.2], vertical_alignment="bottom")
    with filter_cols[0]:
        severity_filter = st.multiselect("Severity", severities, placeholder="All severities", key="severity_filter")
    with filter_cols[1]:
        category_filter = st.multiselect("Category", categories, placeholder="All categories", key="category_filter")
    with filter_cols[2]:
        st.caption(f"Showing {len(findings)} analyzer findings")

    filtered = [
        item
        for item in findings
        if (not severity_filter or finding_severity(item).capitalize() in severity_filter)
        and (not category_filter or finding_category(item) in category_filter)
    ]
    if not filtered:
        st.info("No findings match the selected filters.", icon=":material/filter_alt_off:")
        return
    for index, finding in enumerate(filtered, 1):
        render_finding(finding, index)


def render_methodology(result: Any) -> None:
    methodology = get_value(result, "methodology", "score_methodology", default={})
    health = get_value(result, "health", "health_scores", "scores", default={})
    criteria = get_value(health, "criteria", default={})
    st.markdown('<div class="section-kicker">SCORE METHODOLOGY</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Transparent by design")
        if methodology:
            for label, explanation in (methodology.items() if isinstance(methodology, dict) else [("Analyzer note", methodology)]):
                st.markdown(f"**{label}**")
                st.caption(str(explanation))
        else:
            st.caption("The analyzer did not return a score methodology for this result.")
        if isinstance(criteria, dict) and criteria:
            st.markdown("#### Criteria returned by the analyzer")
            criteria_rows = []
            for name, item in criteria.items():
                criteria_rows.append(
                    {
                        "Criterion": str(name).replace("_", " ").title(),
                        "Status": "Met" if get_value(item, "met", default=False) else "Not met",
                        "Points": f"{get_value(item, 'points', default=0)}/{get_value(item, 'max_points', default='—')}",
                    }
                )
            st.table(criteria_rows)
        st.caption("Scores and criteria shown here are the analyzer response; RepoPilot does not calculate an additional score.")


def render_limitations(result: Any) -> None:
    limitations = as_list(get_value(result, "limitations", default=[]))
    st.markdown('<div class="section-kicker">LIMITATIONS & SCOPE</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if limitations:
            for limitation in limitations:
                st.markdown(f":material/info: {limitation}")
        else:
            st.caption("The analyzer did not return explicit limitations for this result.")


def render_architecture(result: Any) -> None:
    tree = get_value(result, "tree", "file_tree", "architecture", default=None)
    if tree is None:
        tree = [get_value(item, "path", default=item) for item in as_list(get_value(result, "files", default=[]))]
    st.markdown('<div class="section-kicker">REPOSITORY MAP</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if tree is None:
            st.caption("The analyzer did not return a repository tree.")
        elif isinstance(tree, str):
            st.code(tree, language="text")
        else:
            st.json(tree, expanded=False)


def render_dashboard(result: Any, repo_url: str) -> None:
    metadata = get_value(result, "metadata", "overview", default={})
    scores = normalize_scores(result)
    findings = as_list(get_value(result, "findings", "issues", "recommendations"))
    phases = as_list(get_value(result, "phases", "completed_phases", "steps"))
    if not phases:
        phases = [name for name in ("metadata", "tree", "files", "findings", "health") if get_value(result, name) is not None]

    st.markdown('<div class="eyebrow">ANALYSIS COMPLETE / EVIDENCE REVIEW</div>', unsafe_allow_html=True)
    heading_cols = st.columns([4, 1], vertical_alignment="bottom")
    with heading_cols[0]:
        st.title(repo_name(result, repo_url), anchor=False)
        st.markdown(f'<div class="repo-pill">:material/code: {escape(repo_url)}</div>', unsafe_allow_html=True)
    with heading_cols[1]:
        report = make_report(result, repo_url)
        st.download_button(
            "Export report",
            report,
            file_name="repopilot-report.md",
            mime="text/markdown",
            icon=":material/download:",
            type="secondary",
            width="stretch",
        )

    if phases:
        with st.container(border=True):
            phase_cols = st.columns(min(5, len(phases)))
            for col, phase in zip(phase_cols, phases):
                label = phase if isinstance(phase, str) else get_value(phase, "name", "label", default="Phase")
                complete = phase if isinstance(phase, str) else get_value(phase, "completed", "status", default=True)
                icon = "check_circle" if complete not in (False, "pending", "incomplete") else "radio_button_unchecked"
                with col:
                    st.markdown(f":material/{icon}: **{escape(str(label))}**")

    meta_cols = st.columns(4)
    overview_items = [
        ("Language", get_value(metadata, "language", "primary_language", default=primary_language(result))),
        ("Files analyzed", get_value(get_value(result, "limits", default={}), "files_seen", default=get_value(metadata, "files", "file_count", default="—"))),
        ("Open findings", len(findings)),
        ("Default branch", get_value(metadata, "default_branch", "branch", default="—")),
    ]
    for col, (label, value) in zip(meta_cols, overview_items):
        with col:
            st.metric(label, value, border=True)

    if st.session_state.active_view == "Methodology":
        render_methodology(result)
        render_limitations(result)
        return
    if st.session_state.active_view == "History":
        render_history()
        return

    render_executive_summary(result, repo_url, findings, scores)
    render_health(result, scores)
    render_findings(result, findings)
    render_architecture(result)
    render_methodology(result)
    render_limitations(result)


def render_history() -> None:
    st.markdown('<div class="section-kicker">ANALYSIS HISTORY</div>', unsafe_allow_html=True)
    st.markdown("### Recent repository reviews")
    history = st.session_state.history
    if not history:
        st.info("Your completed analyses will appear here in this browser session.", icon=":material/history:")
        return
    for index, item in enumerate(history):
        cols = st.columns([0.16, 3.8, 1.2], vertical_alignment="center")
        with cols[0]:
            st.markdown(f'<div class="history-index">{index + 1:02d}</div>', unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"**{escape(str(item.get('name', 'Repository')))}**")
            st.caption(f"{escape(str(item.get('repo_url', '')))} · {escape(str(item.get('analyzed_at', '')))}")
        with cols[2]:
            if st.button("Open review", key=f"history_{index}", icon=":material/arrow_forward:"):
                st.session_state.result = item["result"]
                st.session_state.repo_url = item["repo_url"]
                st.session_state.active_view = "Analyze"
                st.rerun()


st.set_page_config(
    page_title="RepoPilot · Repository intelligence",
    page_icon=":material/terminal:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()
init_state()

if not render_auth():
    st.stop()

render_sidebar()

if st.session_state.active_view == "History" and st.session_state.result is None:
    render_history()
elif st.session_state.active_view == "Methodology" and st.session_state.result is None:
    st.markdown('<div class="eyebrow">REPOPILOT / HOW IT WORKS</div>', unsafe_allow_html=True)
    st.title("A transparent review workflow", anchor=False)
    st.markdown('<p class="hero-lede">RepoPilot keeps the analysis surface intentionally small: inspect a bounded public repository, show the returned signals, and keep every finding tied to evidence.</p>', unsafe_allow_html=True)
    render_methodology({})
    render_limitations({})
elif st.session_state.result is None:
    render_landing()
else:
    render_dashboard(st.session_state.result, st.session_state.repo_url)
