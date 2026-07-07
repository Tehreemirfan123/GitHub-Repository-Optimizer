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

from app.agents.documentation_agent import analyze_repository_documentation
from app.agents.repository_agent import analyze_public_repository
from app.guardrails.input_policy import (
    InputPolicyError,
    validate_public_github_repository_url,
)


st.set_page_config(
    page_title="GitHub Repository Optimizer",
    page_icon="🔍",
    layout="wide",
)


def _initialize_session_state() -> None:
    """Initialize stable Streamlit session-state fields."""
    defaults: dict[str, Any] = {
        "repository_result": None,
        "documentation_result": None,
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


def _build_priority_recommendations(
    repository_result: dict[str, Any],
    documentation_result: dict[str, Any],
) -> list[dict[str, str]]:
    """Combine and de-duplicate recommendations from both analyses."""
    recommendations: list[dict[str, str]] = []
    seen_recommendations: set[str] = set()

    priority_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }

    for missing_artifact in _safe_list(
        repository_result.get("missing_artifacts")
    ):
        artifact = str(missing_artifact.get("artifact", "Repository artifact"))
        recommendation = str(missing_artifact.get("reason", "")).strip()
        priority = str(missing_artifact.get("priority", "medium")).lower()

        if not recommendation:
            continue

        key = f"{artifact}:{recommendation}".lower()

        if key not in seen_recommendations:
            recommendations.append(
                {
                    "priority": priority,
                    "artifact": artifact,
                    "recommendation": recommendation,
                    "rationale": (
                        "Identified from repository structure analysis."
                    ),
                }
            )
            seen_recommendations.add(key)

    for recommendation_item in _safe_list(
        documentation_result.get("recommendations")
    ):
        artifact = str(recommendation_item.get("artifact", "Documentation"))
        recommendation = str(
            recommendation_item.get("recommendation", "")
        ).strip()
        priority = str(
            recommendation_item.get("priority", "medium")
        ).lower()
        rationale = str(recommendation_item.get("rationale", "")).strip()

        if not recommendation:
            continue

        key = f"{artifact}:{recommendation}".lower()

        if key not in seen_recommendations:
            recommendations.append(
                {
                    "priority": priority,
                    "artifact": artifact,
                    "recommendation": recommendation,
                    "rationale": rationale,
                }
            )
            seen_recommendations.add(key)

    return sorted(
        recommendations,
        key=lambda item: priority_order.get(item["priority"], 99),
    )


def _display_repository_summary(result: dict[str, Any]) -> None:
    """Display the high-level repository summary."""
    st.subheader("Repository Summary")

    repository_name = result.get("repository_name", "Unknown")
    owner = result.get("owner", "Unknown")
    project_type = str(result.get("project_type", "unknown")).replace("_", " ")
    primary_language = result.get("primary_language") or "Not detected"
    repository_url = result.get("repository_url", "")

    column_one, column_two, column_three, column_four = st.columns(4)

    column_one.metric("Repository", repository_name)
    column_two.metric("Owner", owner)
    column_three.metric("Project Type", project_type.title())
    column_four.metric("Primary Language", primary_language)

    if isinstance(repository_url, str) and repository_url:
        st.link_button("Open Repository on GitHub", repository_url)


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
    repository_result: dict[str, Any],
    documentation_result: dict[str, Any],
) -> None:
    """Display merged repository and documentation recommendations."""
    st.subheader("Recommendations")

    recommendations = _build_priority_recommendations(
        repository_result=repository_result,
        documentation_result=documentation_result,
    )

    if not recommendations:
        st.success("No recommendations were generated by the current checks.")
        return

    for item in recommendations:
        priority = item["priority"].upper()
        artifact = item["artifact"]
        recommendation = item["recommendation"]
        rationale = item["rationale"]

        if item["priority"] == "high":
            container = st.error
        elif item["priority"] == "medium":
            container = st.warning
        else:
            container = st.info

        container(
            f"**{priority} · {artifact}**\n\n"
            f"{recommendation}\n\n"
            f"*Why:* {rationale}"
        )


def _display_limitations(
    repository_result: dict[str, Any],
    documentation_result: dict[str, Any],
) -> None:
    """Display deduplicated limitations from both analysis functions."""
    limitations: list[str] = []

    for result in (repository_result, documentation_result):
        for limitation in result.get("limitations", []):
            if isinstance(limitation, str) and limitation not in limitations:
                limitations.append(limitation)

    if not limitations:
        return

    with st.expander("Analysis Limitations"):
        for limitation in limitations:
            st.markdown(f"- {limitation}")


def _run_analysis(repository_url: str) -> None:
    """Run both existing specialist analysis functions safely."""
    try:
        validated_reference = validate_public_github_repository_url(
            repository_url
        )
    except InputPolicyError as error:
        st.error(str(error))
        return

    normalized_url = validated_reference.normalized_url

    progress = st.progress(0, text="Validating repository URL...")

    try:
        progress.progress(25, text="Running repository structure analysis...")
        repository_result = analyze_public_repository(normalized_url)

        progress.progress(65, text="Running documentation analysis...")
        documentation_result = analyze_repository_documentation(normalized_url)

        progress.progress(100, text="Analysis completed.")

        st.session_state.repository_result = repository_result
        st.session_state.documentation_result = documentation_result
        st.session_state.last_repository_url = normalized_url

    except Exception:
        st.error(
            "The application could not complete the analysis safely. "
            "Check your connection, GitHub token, and terminal logs."
        )
    finally:
        progress.empty()


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

    repository_result = st.session_state.repository_result
    documentation_result = st.session_state.documentation_result

    if not isinstance(repository_result, dict):
        st.info(
            "Enter a public GitHub repository URL and click "
            "**Analyze Repository**."
        )
        return

    if not repository_result.get("success", False):
        _display_error_result(
            repository_result,
            "Repository analysis failed",
        )
        return

    if not isinstance(documentation_result, dict):
        st.warning(
            "Repository analysis completed, but documentation analysis "
            "did not return a result."
        )
        _display_repository_summary(repository_result)
        _display_repository_analysis(repository_result)
        return

    if not documentation_result.get("success", False):
        _display_error_result(
            documentation_result,
            "Documentation analysis failed",
        )
        _display_repository_summary(repository_result)
        _display_repository_analysis(repository_result)
        return

    _display_repository_summary(repository_result)
    st.divider()

    _display_repository_analysis(repository_result)
    st.divider()

    _display_documentation_analysis(documentation_result)
    st.divider()

    _display_recommendations(
        repository_result=repository_result,
        documentation_result=documentation_result,
    )
    st.divider()

    _display_limitations(
        repository_result=repository_result,
        documentation_result=documentation_result,
    )


if __name__ == "__main__":
    main()