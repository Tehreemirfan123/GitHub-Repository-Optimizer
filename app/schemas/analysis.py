"""Shared schemas for the unified repository-analysis workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AnalysisProfile(str, Enum):
    """Supported analysis profiles."""

    STANDARD = "standard"


class AnalysisStatus(str, Enum):
    """Overall analysis execution status."""

    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class AgentExecutionStatus(str, Enum):
    """Execution status for one analysis component."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Priority(str, Enum):
    """Normalized recommendation priority."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisError(BaseModel):
    """Safe application-level error."""

    error_code: str
    message: str
    component: str | None = None


class RepositorySnapshot(BaseModel):
    """Repository identity and metadata used in a report."""

    owner: str
    name: str
    url: str
    description: str | None = None
    default_branch: str
    primary_language: str | None = None
    topics: list[str] = Field(default_factory=list)
    stars: int = Field(default=0, ge=0)
    forks: int = Field(default=0, ge=0)


class AnalysisLimits(BaseModel):
    """Retrieval and sampling information."""

    file_count_retrieved: int = Field(default=0, ge=0)
    file_tree_truncated: bool = False
    readme_available: bool = False
    readme_truncated: bool = False
    redacted_secret_count: int = Field(default=0, ge=0)


class ComponentResult(BaseModel):
    """Result returned by one specialist analysis component."""

    component_name: str
    status: AgentExecutionStatus
    result: dict[str, Any] | None = None
    error: AnalysisError | None = None


class UnifiedRecommendation(BaseModel):
    """Normalized recommendation used by every presentation layer."""

    recommendation_id: str
    category: str
    artifact: str
    priority: Priority
    recommendation: str
    rationale: str
    sources: list[str] = Field(default_factory=list)


class CategoryScore(BaseModel):
    """Temporary deterministic Phase 1 category score."""

    category: str
    score: int = Field(ge=0, le=100)
    finding_count: int = Field(default=0, ge=0)
    scoring_note: str


class RepositoryHealthScore(BaseModel):
    """Temporary Phase 1 repository health score."""

    overall_score: int = Field(ge=0, le=100)
    categories: list[CategoryScore] = Field(default_factory=list)
    scoring_version: str = "phase-1.0"
    disclaimer: str = (
        "This is a preliminary heuristic score based only on the currently "
        "implemented repository-structure and documentation checks."
    )


class RepositoryAnalysisReport(BaseModel):
    """Canonical result returned by Streamlit, ADK, API, and CLI clients."""

    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    analysis_profile: AnalysisProfile
    status: AnalysisStatus
    repository: RepositorySnapshot | None = None
    limits: AnalysisLimits | None = None
    components: list[ComponentResult] = Field(default_factory=list)
    recommendations: list[UnifiedRecommendation] = Field(default_factory=list)
    score: RepositoryHealthScore | None = None
    limitations: list[str] = Field(default_factory=list)
    errors: list[AnalysisError] = Field(default_factory=list)