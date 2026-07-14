"""Repository Analysis Agent and deterministic repository-analysis tool.

Responsibilities:
- Call GitHub retrieval tool.
- Infer project type from repository metadata, README, and file tree.
- Detect languages and common framework signals.
- Identify high-value missing repository files.
- Return structured findings.

This module does not perform documentation scoring, security scanning,
discoverability scoring, or portfolio assessment.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from google.adk import Agent
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.prompts.repository_prompt import REPOSITORY_AGENT_INSTRUCTION
from app.tools.github_tool import RepositoryData, fetch_github_repository


LOGGER = logging.getLogger(__name__)


class ConfidenceLevel(str, Enum):
    """Confidence level for evidence-based repository findings."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProjectType(str, Enum):
    """Supported high-level repository classifications."""

    STREAMLIT_APPLICATION = "streamlit_application"
    WEB_APPLICATION = "web_application"
    BACKEND_API = "backend_api"
    PYTHON_PACKAGE = "python_package"
    MACHINE_LEARNING_PROJECT = "machine_learning_project"
    DATA_SCIENCE_PROJECT = "data_science_project"
    CLI_TOOL = "cli_tool"
    GENERAL_SOFTWARE_PROJECT = "general_software_project"


class EvidenceItem(BaseModel):
    """One evidence item supporting a repository finding."""

    source: str = Field(
        description="Where the evidence was found, such as file tree or README."
    )
    detail: str = Field(
        description="Safe summary of the evidence."
    )


class TechnologySignal(BaseModel):
    """Detected language or framework signal."""

    name: str
    category: str = Field(
        description="Examples: language, framework, runtime, package_manager."
    )
    confidence: ConfidenceLevel
    evidence: list[EvidenceItem] = Field(default_factory=list)


class MissingArtifact(BaseModel):
    """A useful repository file or folder that was not detected."""

    artifact: str
    reason: str
    priority: str = Field(
        description="Suggested priority: high, medium, or low."
    )


class RepositoryStructureFinding(BaseModel):
    """A repository structure observation."""

    title: str
    category: str = Field(
        description="Examples: structure, project_type, maintainability."
    )
    summary: str
    confidence: ConfidenceLevel
    evidence: list[EvidenceItem] = Field(default_factory=list)


class RepositoryAnalysisResult(BaseModel):
    """Validated Phase 3 repository analysis output."""

    success: bool = True
    repository_url: str
    repository_name: str
    owner: str
    project_type: ProjectType
    primary_language: str | None = None
    detected_technologies: list[TechnologySignal] = Field(default_factory=list)
    structure_findings: list[RepositoryStructureFinding] = Field(
        default_factory=list
    )
    missing_artifacts: list[MissingArtifact] = Field(default_factory=list)
    file_count_inspected: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


def _normalized_paths(file_tree: list[dict[str, Any]]) -> set[str]:
    """Return normalized lowercase file paths from GitHub tree entries."""
    return {
        # pyrefly: ignore [unnecessary-type-conversion]
        str(entry["path"]).lower()
        for entry in file_tree
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def _has_directory(paths: set[str], directory_name: str) -> bool:
    """Check whether a directory appears in a flattened GitHub tree."""
    normalized_directory = directory_name.strip("/").lower()
    directory_prefix = f"{normalized_directory}/"

    return any(
        path == normalized_directory or path.startswith(directory_prefix)
        for path in paths
    )


def _readme_contains(readme: str | None, *terms: str) -> bool:
    """Return True when any lowercased term appears in README text."""
    if not readme:
        return False

    normalized_readme = readme.lower()
    return any(term.lower() in normalized_readme for term in terms)


def _detect_project_type(
    paths: set[str],
    readme_content: str | None,
) -> tuple[ProjectType, list[EvidenceItem]]:
    """Infer project type using safe, observable repository signals."""
    evidence: list[EvidenceItem] = []

    if (
        "streamlit" in (readme_content or "").lower()
        or "streamlit_app.py" in paths
    ):
        evidence.append(
            EvidenceItem(
                source="repository_evidence",
                detail="Streamlit was referenced in the README or streamlit_app.py exists.",
            )
        )
        return ProjectType.STREAMLIT_APPLICATION, evidence

    if any(path.endswith(".ipynb") for path in paths):
        evidence.append(
            EvidenceItem(
                source="file_tree",
                detail="One or more Jupyter notebook files were found.",
            )
        )
        return ProjectType.DATA_SCIENCE_PROJECT, evidence

    if (
        _readme_contains(readme_content, "pytorch", "tensorflow", "scikit-learn")
        or any(
            marker in paths
            for marker in {"train.py", "predict.py", "inference.py", "model.py"}
        )
    ):
        evidence.append(
            EvidenceItem(
                source="repository_evidence",
                detail="Machine learning library references or model-related scripts were found.",
            )
        )
        return ProjectType.MACHINE_LEARNING_PROJECT, evidence

    if (
        _readme_contains(readme_content, "fastapi", "flask", "django")
        or "main.py" in paths
        and any(
            keyword in (readme_content or "").lower()
            for keyword in ("api", "fastapi", "flask")
        )
    ):
        evidence.append(
            EvidenceItem(
                source="repository_evidence",
                detail="API framework references were found in repository evidence.",
            )
        )
        return ProjectType.BACKEND_API, evidence

    if "pyproject.toml" in paths and _has_directory(paths, "src"):
        evidence.append(
            EvidenceItem(
                source="file_tree",
                detail="pyproject.toml and a src/ directory were found.",
            )
        )
        return ProjectType.PYTHON_PACKAGE, evidence

    if "package.json" in paths and (
        _has_directory(paths, "src") or "vite.config.ts" in paths
    ):
        evidence.append(
            EvidenceItem(
                source="file_tree",
                detail="package.json and common frontend project structure were found.",
            )
        )
        return ProjectType.WEB_APPLICATION, evidence

    if any(path.endswith("cli.py") for path in paths) or "click" in (
        readme_content or ""
    ).lower():
        evidence.append(
            EvidenceItem(
                source="repository_evidence",
                detail="CLI-related file or README reference was found.",
            )
        )
        return ProjectType.CLI_TOOL, evidence

    evidence.append(
        EvidenceItem(
            source="repository_evidence",
            detail="No strong framework-specific repository pattern was found.",
        )
    )
    return ProjectType.GENERAL_SOFTWARE_PROJECT, evidence


def _detect_technologies(
    primary_language: str | None,
    paths: set[str],
    readme_content: str | None,
) -> list[TechnologySignal]:
    """Detect programming language and framework signals from safe evidence."""
    technologies: list[TechnologySignal] = []

    if primary_language:
        technologies.append(
            TechnologySignal(
                name=primary_language,
                category="language",
                confidence=ConfidenceLevel.HIGH,
                evidence=[
                    EvidenceItem(
                        source="github_metadata",
                        detail=f"GitHub reports the primary language as {primary_language}.",
                    )
                ],
            )
        )

    framework_rules: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        ("Streamlit", ("streamlit_app.py",), ("streamlit",)),
        ("FastAPI", (), ("fastapi",)),
        ("Flask", (), ("flask",)),
        ("Django", ("manage.py",), ("django",)),
        ("React", (), ("react",)),
        ("Next.js", ("next.config.js", "next.config.ts"), ("next.js",)),
        ("Docker", ("dockerfile", "docker-compose.yml", "compose.yml"), ("docker",)),
    ]

    readme_lower = (readme_content or "").lower()

    for framework_name, path_markers, readme_markers in framework_rules:
        matching_paths = [
            marker for marker in path_markers if marker.lower() in paths
        ]
        matching_readme_markers = [
            marker for marker in readme_markers if marker.lower() in readme_lower
        ]

        if not matching_paths and not matching_readme_markers:
            continue

        evidence: list[EvidenceItem] = []

        if matching_paths:
            evidence.append(
                EvidenceItem(
                    source="file_tree",
                    detail=f"Detected file marker(s): {', '.join(matching_paths)}.",
                )
            )

        if matching_readme_markers:
            evidence.append(
                EvidenceItem(
                    source="README",
                    detail=f"Detected README reference(s): {', '.join(matching_readme_markers)}.",
                )
            )

        technologies.append(
            TechnologySignal(
                name=framework_name,
                category="framework",
                confidence=(
                    ConfidenceLevel.HIGH
                    if matching_paths
                    else ConfidenceLevel.MEDIUM
                ),
                evidence=evidence,
            )
        )

    return technologies


def _find_missing_artifacts(
    paths: set[str],
    project_type: ProjectType,
) -> list[MissingArtifact]:
    """Identify only baseline repository artifacts relevant to Phase 3."""
    missing_artifacts: list[MissingArtifact] = []

    required_baseline: list[tuple[str, str, str]] = [
        (
            "README.md",
            "A README helps users understand setup and usage.",
            "high",
        ),
        (
            ".gitignore",
            "A .gitignore helps prevent local and generated files from being committed.",
            "high",
        ),
        (
            "LICENSE",
            "A license clarifies reuse permissions for public repositories.",
            "medium",
        ),
    ]

    for artifact, reason, priority in required_baseline:
        if artifact.lower() not in paths:
            missing_artifacts.append(
                MissingArtifact(
                    artifact=artifact,
                    reason=reason,
                    priority=priority,
                )
            )

    if project_type in {
        ProjectType.WEB_APPLICATION,
        ProjectType.BACKEND_API,
        ProjectType.STREAMLIT_APPLICATION,
        ProjectType.MACHINE_LEARNING_PROJECT,
    } and not (
        _has_directory(paths, "tests")
        or _has_directory(paths, "test")
    ):
        missing_artifacts.append(
            MissingArtifact(
                artifact="tests/",
                reason="No conventional test directory was detected.",
                priority="medium",
            )
        )

    if not _has_directory(paths, ".github/workflows"):
        missing_artifacts.append(
            MissingArtifact(
                artifact=".github/workflows/",
                reason="No GitHub Actions workflow directory was detected.",
                priority="low",
            )
        )

    return missing_artifacts


def _build_structure_findings(
    paths: set[str],
    project_type: ProjectType,
    project_type_evidence: list[EvidenceItem],
) -> list[RepositoryStructureFinding]:
    """Build structured, evidence-based repository structure findings."""
    findings: list[RepositoryStructureFinding] = [
        RepositoryStructureFinding(
            title="Detected project type",
            category="project_type",
            summary=f"The repository is classified as {project_type.value}.",
            confidence=ConfidenceLevel.MEDIUM,
            evidence=project_type_evidence,
        )
    ]

    if _has_directory(paths, "src"):
        findings.append(
            RepositoryStructureFinding(
                title="Source directory detected",
                category="structure",
                summary="A src/ directory was detected for source code organization.",
                confidence=ConfidenceLevel.HIGH,
                evidence=[
                    EvidenceItem(
                        source="file_tree",
                        detail="A src/ directory or files beneath src/ were found.",
                    )
                ],
            )
        )

    if _has_directory(paths, "tests") or _has_directory(paths, "test"):
        findings.append(
            RepositoryStructureFinding(
                title="Test directory detected",
                category="structure",
                summary="A conventional test directory was detected.",
                confidence=ConfidenceLevel.HIGH,
                evidence=[
                    EvidenceItem(
                        source="file_tree",
                        detail="A tests/ or test/ directory was found.",
                    )
                ],
            )
        )

    if _has_directory(paths, ".github"):
        findings.append(
            RepositoryStructureFinding(
                title="GitHub configuration directory detected",
                category="structure",
                summary="A .github/ directory was detected.",
                confidence=ConfidenceLevel.HIGH,
                evidence=[
                    EvidenceItem(
                        source="file_tree",
                        detail="A .github/ directory or files beneath it were found.",
                    )
                ],
            )
        )

    return findings

def analyze_repository_context(
    repository_data: RepositoryData,
) -> dict[str, Any]:
    """Structurally analyze already-fetched repository context."""
    try:
        repository_payload = repository_data.model_dump(mode="json")

        metadata = repository_payload["metadata"]
        repository = repository_payload["repository"]
        readme = repository_payload["readme"]
        file_tree = repository_payload.get("file_tree", [])
        limitations = list(
            repository_payload.get("limitations", [])
        )

        paths = _normalized_paths(file_tree)
        readme_content = readme.get("content")

        project_type, project_type_evidence = _detect_project_type(
            paths=paths,
            readme_content=readme_content,
        )

        technologies = _detect_technologies(
            primary_language=metadata.get("language"),
            paths=paths,
            readme_content=readme_content,
        )

        result = RepositoryAnalysisResult(
            repository_url=str(repository["url"]),
            repository_name=str(metadata["name"]),
            owner=str(metadata["owner"]),
            project_type=project_type,
            primary_language=metadata.get("language"),
            detected_technologies=technologies,
            structure_findings=_build_structure_findings(
                paths=paths,
                project_type=project_type,
                project_type_evidence=project_type_evidence,
            ),
            missing_artifacts=_find_missing_artifacts(
                paths=paths,
                project_type=project_type,
            ),
            file_count_inspected=len(file_tree),
            limitations=[
                *limitations,
                (
                    "Analysis is based on repository metadata, README content, "
                    "and the retrieved file tree only."
                ),
                (
                    "This phase does not inspect source-code contents beyond "
                    "README text."
                ),
            ],
        )

        LOGGER.info(
            "repository_analysis_completed",
            extra={
                "repository": result.repository_name,
                "owner": result.owner,
                "project_type": result.project_type.value,
                "file_count_inspected": result.file_count_inspected,
            },
        )

        return result.model_dump(mode="json")

    except Exception as error:
        LOGGER.exception(
            "repository_analysis_failed",
            extra={"error_type": type(error).__name__},
        )

        return {
            "success": False,
            "error_code": "repository_analysis_failed",
            "message": "Repository analysis could not be completed safely.",
        }


def analyze_public_repository(
    repository_url: str,
) -> dict[str, Any]:
    """Fetch and structurally analyze a public GitHub repository."""
    try:
        repository_payload = fetch_github_repository(repository_url)

        if not repository_payload.get("success", False):
            return repository_payload

        repository_data = RepositoryData.model_validate(
            repository_payload
        )

        return analyze_repository_context(repository_data)

    except Exception as error:
        LOGGER.exception(
            "repository_fetch_for_analysis_failed",
            extra={"error_type": type(error).__name__},
        )

        return {
            "success": False,
            "error_code": "repository_fetch_for_analysis_failed",
            "message": (
                "Repository data could not be retrieved for structure "
                "analysis."
            ),
        }

settings = get_settings()

repository_agent = Agent(
    name="repository_analysis_agent",
    mode="single_turn",
    model=settings.gemini_model,
    description=(
        "Fetches a public GitHub repository and produces evidence-based "
        "structure, technology, and missing-artifact findings."
    ),
    instruction=REPOSITORY_AGENT_INSTRUCTION,
    tools=[analyze_public_repository],
)