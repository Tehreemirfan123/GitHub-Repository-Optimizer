"""Streamlit interface for the GitHub Repository Optimizer Agent.

Responsibilities:
- Accept a public GitHub repository URL.
- Run repository structure analysis.
- Run documentation analysis.
- Display structured findings and recommendations.

This UI does not modify repositories, create pull requests, or expose tokens.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from typing import Any
import streamlit as st

from app.schemas.analysis import (
    AnalysisStatus,
    RepositoryAnalysisReport,
)
from app.services.analysis_service import analysis_service


st.set_page_config(
    page_title="GitHub Repository Optimizer",
    page_icon="🔍",
    layout="wide",
)


def _initialize_session_state() -> None:
    """Initialize Streamlit session-state values."""
    defaults = {
        "analysis_report": None,
        "last_repository_url": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_list(value: object) -> list[dict[str, Any]]:
    """Return a list of dictionaries or an empty list."""
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _display_error_result(result: dict[str, Any], title: str) -> None:
    """Display a safe error returned by an analysis function."""
    error_code = result.get("error_code", "analysis_failed")
    message = result.get(
        "message",
        "The analysis could not be completed safely.",
    )

    st.error(f"{title}: {message}")
    st.caption(f"Error code: `{error_code}`")

def _display_repository_summary(
    report: RepositoryAnalysisReport,
) -> None:
    """Display repository metadata from the canonical report."""
    if report.repository is None:
        return

    st.subheader("Repository Summary")

    repository = report.repository

    column_one, column_two, column_three, column_four = st.columns(4)

    column_one.metric("Repository", repository.name)
    column_two.metric("Owner", repository.owner)
    column_three.metric(
        "Primary Language",
        repository.primary_language or "Not detected",
    )

    if report.score is not None:
        column_four.metric(
            "Preliminary Score",
            f"{report.score.overall_score}/100",
        )
    else:
        column_four.metric("Preliminary Score", "Unavailable")

    st.link_button("Open Repository on GitHub", repository.url)

def _display_score(report: RepositoryAnalysisReport) -> None:
    """Display the preliminary Phase 1 score."""
    if report.score is None:
        return

    st.subheader("Repository Health Score")

    st.metric(
        "Overall Score",
        f"{report.score.overall_score}/100",
    )

    columns = st.columns(max(1, len(report.score.categories)))

    for column, category in zip(
        columns,
        report.score.categories,
        strict=False,
    ):
        with column:
            st.metric(
                category.category.replace("_", " ").title(),
                f"{category.score}/100",
            )
            st.caption(category.scoring_note)

    st.caption(report.score.disclaimer)

def _display_repository_analysis(result: dict[str, Any]) -> None:
    """Display repository structure and technology findings."""
    st.subheader("Repository Analysis")

    technologies = _safe_list(result.get("detected_technologies"))
    findings = _safe_list(result.get("structure_findings"))
    missing_artifacts = _safe_list(result.get("missing_artifacts"))

    left_column, right_column = st.columns(2)

    with left_column:
        st.markdown("#### Detected Technologies")

        if not technologies:
            st.info("No technology signals were detected.")

        for technology in technologies:
            name = technology.get("name", "Unknown technology")
            category = technology.get("category", "signal")
            confidence = technology.get("confidence", "unknown")

            st.markdown(
                f"**{name}**  \n"
                f"Category: `{category}` · Confidence: `{confidence}`"
            )

            for evidence in _safe_list(technology.get("evidence")):
                detail = evidence.get("detail")

                if detail:
                    st.caption(f"Evidence: {detail}")

    with right_column:
        st.markdown("#### Missing or Recommended Files")

        if not missing_artifacts:
            st.success("No baseline missing artifacts were detected.")

        for artifact in missing_artifacts:
            name = artifact.get("artifact", "Unknown artifact")
            reason = artifact.get("reason", "")
            priority = artifact.get("priority", "medium")

            st.warning(
                f"**{name}** · Priority: `{priority}`\n\n{reason}"
            )

    st.markdown("#### Structure Findings")

    if not findings:
        st.info("No structure findings were returned.")

    for finding in findings:
        title = finding.get("title", "Finding")
        summary = finding.get("summary", "")
        confidence = finding.get("confidence", "unknown")

        with st.expander(f"{title} · Confidence: {confidence}"):
            st.write(summary)

            for evidence in _safe_list(finding.get("evidence")):
                detail = evidence.get("detail")

                if detail:
                    st.caption(f"Evidence: {detail}")


def _display_documentation_analysis(result: dict[str, Any]) -> None:
    """Display README and baseline documentation assessments."""
    st.subheader("Documentation Analysis")

    assessments = _safe_list(result.get("assessments"))

    if not assessments:
        st.info("No documentation assessments were returned.")
        return

    columns = st.columns(len(assessments))

    for column, assessment in zip(columns, assessments, strict=False):
        artifact = str(assessment.get("artifact", "Document"))
        status = str(assessment.get("status", "unknown"))

        with column:
            if status == "present":
                st.success(f"{artifact}\n\nPresent")
            elif status == "partial":
                st.warning(f"{artifact}\n\nPartial")
            elif status == "missing":
                st.error(f"{artifact}\n\nMissing")
            else:
                st.info(f"{artifact}\n\nUnavailable")

    for assessment in assessments:
        artifact = assessment.get("artifact", "Document")
        status = assessment.get("status", "unknown")
        summary = assessment.get("summary", "")
        path = assessment.get("path")

        with st.expander(f"{artifact} · {str(status).title()}"):
            if path:
                st.caption(f"Path: `{path}`")

            st.write(summary)

            for evidence in assessment.get("evidence", []):
                if isinstance(evidence, str):
                    st.caption(f"Evidence: {evidence}")

def _display_recommendations(
    report: RepositoryAnalysisReport,
) -> None:
    """Display recommendations already normalized by ReportService."""
    st.subheader("Recommendations")

    if not report.recommendations:
        st.success(
            "No recommendations were generated by the current checks."
        )
        return

    for item in report.recommendations:
        content = (
            f"**{item.priority.value.upper()} · {item.artifact}**\n\n"
            f"{item.recommendation}\n\n"
            f"*Why:* {item.rationale}"
        )

        if item.priority.value == "high":
            st.error(content)
        elif item.priority.value == "medium":
            st.warning(content)
        else:
            st.info(content)

def _display_limitations(
    report: RepositoryAnalysisReport,
) -> None:
    """Display report-level limitations."""
    if not report.limitations:
        return

    with st.expander("Analysis Limitations"):
        for limitation in report.limitations:
            st.markdown(f"- {limitation}")

def _display_analysis_metadata(
    report: RepositoryAnalysisReport,
) -> None:
    """Display reproducibility and coverage information."""
    if report.limits is None:
        return

    with st.expander("Analysis Details"):
        st.write(f"Analysis ID: `{report.analysis_id}`")
        st.write(f"Created: `{report.created_at.isoformat()}`")
        st.write(f"Profile: `{report.analysis_profile.value}`")
        st.write(
            f"Repository files retrieved: "
            f"`{report.limits.file_count_retrieved}`"
        )
        st.write(
            f"File tree truncated: "
            f"`{report.limits.file_tree_truncated}`"
        )
        st.write(
            f"README available: "
            f"`{report.limits.readme_available}`"
        )
        st.write(
            f"README truncated: "
            f"`{report.limits.readme_truncated}`"
        )


def _run_analysis(repository_url: str) -> None:
    """Run repository analysis through the canonical application service."""
    normalized_input = repository_url.strip()

    if not normalized_input:
        st.error("Enter a public GitHub repository URL.")
        return

    progress = st.progress(
        0,
        text="Preparing repository analysis...",
    )

    try:
        progress.progress(
            20,
            text="Retrieving repository context...",
        )

        report = analysis_service.analyze_repository_sync(
            repository_url=normalized_input,
            analysis_profile="standard",
        )

        progress.progress(
            80,
            text="Building optimization report...",
        )

        st.session_state.analysis_report = report
        st.session_state.last_repository_url = normalized_input

        progress.progress(
            100,
            text="Analysis completed.",
        )

    except Exception:
        st.error(
            "The application could not complete the analysis safely."
        )

    finally:
        progress.empty()

def _get_component_result(
    report: RepositoryAnalysisReport,
    component_name: str,
) -> dict[str, Any] | None:
    """Return the result of a completed report component."""
    for component in report.components:
        if (
            component.component_name == component_name
            and component.result is not None
        ):
            return component.result

    return None

def main() -> None:
    """Render the Streamlit application."""
    _initialize_session_state()

    st.title("GitHub Repository Optimizer")
    st.caption(
        "Analyze the structure and documentation of a public GitHub repository."
    )

    with st.form("repository_analysis_form"):
        repository_url = st.text_input(
            "Public GitHub Repository URL",
            placeholder="https://github.com/owner/repository",
            value=st.session_state.last_repository_url or "",
        )

        submitted = st.form_submit_button(
            "Analyze Repository",
            type="primary",
        )

    if submitted:
        _run_analysis(repository_url)

    # if not isinstance(repository_result, dict):
    #     st.info(
    #         "Enter a public GitHub repository URL and click "
    #         "**Analyze Repository**."
    #     )
    #     return

    # if not repository_result.get("success", False):
    #     _display_error_result(
    #         repository_result,
    #         "Repository analysis failed",
    #     )
    #     return

    # if not isinstance(documentation_result, dict):
    #     st.warning(
    #         "Repository analysis completed, but documentation analysis "
    #         "did not return a result."
    #     )
    #     _display_repository_summary(repository_result)
    #     _display_repository_analysis(repository_result)
    #     return

    # if not documentation_result.get("success", False):
    #     _display_error_result(
    #         documentation_result,
    #         "Documentation analysis failed",
    #     )
    #     _display_repository_summary(repository_result)
    #     _display_repository_analysis(repository_result)
    #     return

    # _display_repository_summary(repository_result)
    # st.divider()

    # _display_repository_analysis(repository_result)
    # st.divider()

    # _display_documentation_analysis(documentation_result)
    # st.divider()

    # _display_recommendations(
    #     repository_result=repository_result,
    #     documentation_result=documentation_result,
    # )
    # st.divider()

    # _display_limitations(
    #     repository_result=repository_result,
    #     documentation_result=documentation_result,
    # )

    report = st.session_state.get("analysis_report")

    if not isinstance(report, RepositoryAnalysisReport):
        st.info(
            "Enter a public GitHub repository URL and click "
            "**Analyze Repository**."
        )
        return

    if report.status == AnalysisStatus.FAILED:
        if report.errors:
            for error in report.errors:
                st.error(error.message)
                st.caption(f"Error code: `{error.error_code}`")
        else:
            st.error("The repository analysis failed.")

        return

    if report.status == AnalysisStatus.PARTIALLY_COMPLETED:
        st.warning(
            "The analysis completed with one or more unavailable sections."
        )

    repository_result = _get_component_result(
        report,
        "repository_structure",
    )

    documentation_result = _get_component_result(
        report,
        "documentation",
    )

    _display_repository_summary(report)

    st.divider()
    _display_score(report)

    if repository_result is not None:
        st.divider()
        _display_repository_analysis(repository_result)

    if documentation_result is not None:
        st.divider()
        _display_documentation_analysis(documentation_result)

    st.divider()
    _display_recommendations(report)

    st.divider()
    _display_limitations(report)

    _display_analysis_metadata(report)

if __name__ == "__main__":
    main()