"""Documentation Analysis Agent.

Responsibilities:
- Reuse the GitHub repository retrieval tool.
- Assess README, LICENSE, CONTRIBUTING, and SECURITY coverage.
- Produce structured documentation findings and recommendations.

This module does not perform security scanning, code-quality analysis,
repository scoring, or repository modification.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

from google.adk import Agent
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.prompts.documentation_prompt import DOCUMENTATION_AGENT_INSTRUCTION
from app.tools.github_tool import fetch_github_repository


LOGGER = logging.getLogger(__name__)


class DocumentationStatus(str, Enum):
    """Availability status of a documentation artifact."""

    PRESENT = "present"
    MISSING = "missing"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RecommendationPriority(str, Enum):
    """Priority level for a documentation recommendation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentationArtifactAssessment(BaseModel):
    """Assessment of one expected repository documentation artifact."""

    artifact: str
    status: DocumentationStatus
    path: str | None = None
    summary: str
    evidence: list[str] = Field(default_factory=list)


class DocumentationRecommendation(BaseModel):
    """Evidence-based documentation recommendation."""

    priority: RecommendationPriority
    artifact: str
    recommendation: str
    rationale: str


class DocumentationAnalysisResult(BaseModel):
    """Validated Phase 4 documentation analysis result."""

    success: bool = True
    repository_url: str
    repository_name: str
    owner: str
    assessments: list[DocumentationArtifactAssessment]
    recommendations: list[DocumentationRecommendation]
    limitations: list[str] = Field(default_factory=list)


def _normalized_path_map(file_tree: list[dict[str, Any]]) -> dict[str, str]:
    """Map lowercase paths to their original GitHub file-tree paths."""
    path_map: dict[str, str] = {}

    for entry in file_tree:
        if not isinstance(entry, dict):
            continue

        path = entry.get("path")

        if isinstance(path, str):
            path_map[path.lower()] = path

    return path_map


def _find_root_file(
    path_map: dict[str, str],
    candidates: tuple[str, ...],
) -> str | None:
    """Find a documentation file located at repository root."""
    for candidate in candidates:
        path = path_map.get(candidate.lower())

        if path is not None:
            return path

    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Return whether text contains at least one normalized search term."""
    normalized_text = text.lower()
    return any(term.lower() in normalized_text for term in terms)


def _readme_headings(readme_content: str) -> set[str]:
    """Extract simple Markdown headings from README text."""
    headings: set[str] = set()

    for line in readme_content.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)

        if match:
            headings.add(match.group(1).strip().lower())

    return headings


def _assess_readme(
    readme: dict[str, Any],
) -> tuple[
    DocumentationArtifactAssessment,
    list[DocumentationRecommendation],
]:
    """Assess README availability and basic onboarding coverage."""
    recommendations: list[DocumentationRecommendation] = []

    if not bool(readme.get("available")):
        assessment = DocumentationArtifactAssessment(
            artifact="README",
            status=DocumentationStatus.MISSING,
            summary="No README was available through the GitHub REST API.",
            evidence=[],
        )

        recommendations.append(
            DocumentationRecommendation(
                priority=RecommendationPriority.HIGH,
                artifact="README",
                recommendation=(
                    "Create a README with project purpose, installation steps, "
                    "usage instructions, and key features."
                ),
                rationale=(
                    "A README is the primary onboarding document for public "
                    "repository visitors."
                ),
            )
        )

        return assessment, recommendations

    readme_content = readme.get("content")

    if not isinstance(readme_content, str) or not readme_content.strip():
        assessment = DocumentationArtifactAssessment(
            artifact="README",
            status=DocumentationStatus.PARTIAL,
            path=readme.get("path"),
            summary="README metadata exists, but readable content was unavailable.",
            evidence=[],
        )

        recommendations.append(
            DocumentationRecommendation(
                priority=RecommendationPriority.HIGH,
                artifact="README",
                recommendation=(
                    "Ensure the README contains readable project overview, "
                    "installation, and usage content."
                ),
                rationale=(
                    "Repository visitors need accessible setup and usage guidance."
                ),
            )
        )

        return assessment, recommendations

    headings = _readme_headings(readme_content)
    has_installation = _contains_any(
        readme_content,
        ("installation", "install", "setup", "getting started"),
    )
    has_usage = _contains_any(
        readme_content,
        ("usage", "quick start", "quickstart", "examples"),
    )
    has_requirements = _contains_any(
        readme_content,
        ("requirements", "prerequisites", "dependencies"),
    )

    missing_sections: list[str] = []

    if not has_installation:
        missing_sections.append("installation or setup instructions")

    if not has_usage:
        missing_sections.append("usage or quick-start instructions")

    if not has_requirements:
        missing_sections.append("requirements or prerequisites")

    if missing_sections:
        assessment = DocumentationArtifactAssessment(
            artifact="README",
            status=DocumentationStatus.PARTIAL,
            path=readme.get("path"),
            summary=(
                "README exists but appears to have incomplete developer "
                "onboarding coverage."
            ),
            evidence=[
                f"Detected Markdown headings: {len(headings)}.",
                f"Missing coverage signals: {', '.join(missing_sections)}.",
            ],
        )

        recommendations.append(
            DocumentationRecommendation(
                priority=RecommendationPriority.HIGH,
                artifact="README",
                recommendation=(
                    "Add clearly labeled sections for "
                    f"{', '.join(missing_sections)}."
                ),
                rationale=(
                    "Clear onboarding documentation reduces friction for users "
                    "and contributors."
                ),
            )
        )
    else:
        assessment = DocumentationArtifactAssessment(
            artifact="README",
            status=DocumentationStatus.PRESENT,
            path=readme.get("path"),
            summary=(
                "README includes basic signals for setup, usage, and "
                "requirements coverage."
            ),
            evidence=[
                f"Detected Markdown headings: {len(headings)}.",
                "Detected setup, usage, and requirements-related content.",
            ],
        )

    return assessment, recommendations


def _assess_standard_file(
    artifact: str,
    path: str | None,
    present_summary: str,
    missing_summary: str,
    recommendation: str,
    rationale: str,
    priority: RecommendationPriority,
) -> tuple[
    DocumentationArtifactAssessment,
    list[DocumentationRecommendation],
]:
    """Assess existence of a standard root-level documentation artifact."""
    if path is not None:
        return (
            DocumentationArtifactAssessment(
                artifact=artifact,
                status=DocumentationStatus.PRESENT,
                path=path,
                summary=present_summary,
                evidence=[f"Detected root-level file: {path}."],
            ),
            [],
        )

    return (
        DocumentationArtifactAssessment(
            artifact=artifact,
            status=DocumentationStatus.MISSING,
            summary=missing_summary,
            evidence=[],
        ),
        [
            DocumentationRecommendation(
                priority=priority,
                artifact=artifact,
                recommendation=recommendation,
                rationale=rationale,
            )
        ],
    )


def analyze_repository_documentation(repository_url: str) -> dict[str, Any]:
    """Analyze baseline documentation coverage for a public GitHub repository.

    Args:
        repository_url: Public HTTPS GitHub URL in the form:
            https://github.com/owner/repository

    Returns:
        Structured assessment of README, LICENSE, CONTRIBUTING, and SECURITY.

    Important:
        This Phase 4 tool does not perform source-code analysis, vulnerability
        scanning, scoring, or repository modification.
    """
    try:
        repository_data = fetch_github_repository(repository_url)

        if not repository_data.get("success", False):
            return repository_data

        metadata = repository_data["metadata"]
        repository = repository_data["repository"]
        readme = repository_data["readme"]
        file_tree = repository_data.get("file_tree", [])
        limitations = list(repository_data.get("limitations", []))

        path_map = _normalized_path_map(file_tree)

        readme_assessment, readme_recommendations = _assess_readme(readme)

        license_path = _find_root_file(
            path_map,
            ("license", "license.md", "license.txt", "copying"),
        )
        license_assessment, license_recommendations = _assess_standard_file(
            artifact="LICENSE",
            path=license_path,
            present_summary=(
                "A root-level license file was detected."
            ),
            missing_summary=(
                "No standard root-level license file was detected."
            ),
            recommendation=(
                "Add a LICENSE file that clearly states repository reuse terms."
            ),
            rationale=(
                "A license clarifies how others may use, modify, and distribute "
                "the project."
            ),
            priority=RecommendationPriority.MEDIUM,
        )

        contributing_path = _find_root_file(
            path_map,
            ("contributing.md", "contributing.rst", "contributing.txt"),
        )
        contributing_assessment, contributing_recommendations = (
            _assess_standard_file(
                artifact="CONTRIBUTING",
                path=contributing_path,
                present_summary=(
                    "A root-level contributing guide was detected."
                ),
                missing_summary=(
                    "No standard root-level contributing guide was detected."
                ),
                recommendation=(
                    "Add CONTRIBUTING.md with local setup, testing, branch, "
                    "and pull-request guidance."
                ),
                rationale=(
                    "Contributor guidance makes external contributions more "
                    "consistent and easier to review."
                ),
                priority=RecommendationPriority.MEDIUM,
            )
        )

        security_path = _find_root_file(
            path_map,
            ("security.md", "security.rst", "security.txt"),
        )
        security_assessment, security_recommendations = _assess_standard_file(
            artifact="SECURITY",
            path=security_path,
            present_summary=(
                "A root-level security policy file was detected."
            ),
            missing_summary=(
                "No standard root-level security policy file was detected."
            ),
            recommendation=(
                "Add SECURITY.md with a responsible vulnerability-reporting "
                "process and supported-version policy."
            ),
            rationale=(
                "A security policy gives researchers and users a clear path "
                "for reporting vulnerabilities responsibly."
            ),
            priority=RecommendationPriority.MEDIUM,
        )

        result = DocumentationAnalysisResult(
            repository_url=str(repository["url"]),
            repository_name=str(metadata["name"]),
            owner=str(metadata["owner"]),
            assessments=[
                readme_assessment,
                license_assessment,
                contributing_assessment,
                security_assessment,
            ],
            recommendations=[
                *readme_recommendations,
                *license_recommendations,
                *contributing_recommendations,
                *security_recommendations,
            ],
            limitations=[
                *limitations,
                (
                    "README content is inspected when available; LICENSE, "
                    "CONTRIBUTING, and SECURITY are currently assessed for "
                    "standard root-level file presence."
                ),
                (
                    "This phase does not validate legal wording, contributor "
                    "policy quality, or security-policy content."
                ),
            ],
        )

        LOGGER.info(
            "documentation_analysis_completed",
            extra={
                "repository": result.repository_name,
                "owner": result.owner,
                "recommendation_count": len(result.recommendations),
            },
        )

        return result.model_dump(mode="json")

    except Exception as error:
        LOGGER.exception(
            "documentation_analysis_failed",
            extra={"error_type": type(error).__name__},
        )

        return {
            "success": False,
            "error_code": "documentation_analysis_failed",
            "message": "Documentation analysis could not be completed safely.",
        }


settings = get_settings()

documentation_agent = Agent(
    name="documentation_analysis_agent",
    mode="single_turn",
    model=settings.gemini_model,
    description=(
        "Analyzes baseline public repository documentation coverage and "
        "produces evidence-based documentation recommendations."
    ),
    instruction=DOCUMENTATION_AGENT_INSTRUCTION,
    tools=[analyze_repository_documentation],
)