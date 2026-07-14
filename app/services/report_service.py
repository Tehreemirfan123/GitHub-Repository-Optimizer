"""Report construction, normalization, deduplication, and scoring."""

from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.analysis import (
    AnalysisLimits,
    AnalysisProfile,
    AnalysisStatus,
    CategoryScore,
    ComponentResult,
    Priority,
    RepositoryAnalysisReport,
    RepositoryHealthScore,
    RepositorySnapshot,
    UnifiedRecommendation,
)
from app.tools.github_tool import RepositoryData


class ReportService:
    """Build the canonical report returned to every client."""

    def build_report(
        self,
        *,
        repository_data: RepositoryData,
        analysis_profile: AnalysisProfile,
        repository_result: dict[str, Any],
        documentation_result: dict[str, Any],
        components: list[ComponentResult],
    ) -> RepositoryAnalysisReport:
        """Create one validated repository-analysis report."""
        recommendations = self._build_recommendations(
            repository_result=repository_result,
            documentation_result=documentation_result,
        )

        limitations = self._merge_limitations(
            repository_data=repository_data,
            repository_result=repository_result,
            documentation_result=documentation_result,
        )

        score = self._calculate_preliminary_score(
            repository_result=repository_result,
            documentation_result=documentation_result,
        )

        return RepositoryAnalysisReport(
            analysis_profile=analysis_profile,
            status=AnalysisStatus.COMPLETED,
            repository=self._build_repository_snapshot(repository_data),
            limits=self._build_analysis_limits(repository_data),
            components=components,
            recommendations=recommendations,
            score=score,
            limitations=limitations,
        )

    @staticmethod
    def _build_repository_snapshot(
        repository_data: RepositoryData,
    ) -> RepositorySnapshot:
        """Convert retrieval data into report repository metadata."""
        return RepositorySnapshot(
            owner=repository_data.repository.owner,
            name=repository_data.repository.repository,
            url=str(repository_data.repository.url),
            description=repository_data.metadata.description,
            default_branch=repository_data.metadata.default_branch,
            primary_language=repository_data.metadata.language,
            topics=repository_data.metadata.topics,
            stars=repository_data.metadata.stars,
            forks=repository_data.metadata.forks,
        )

    @staticmethod
    def _build_analysis_limits(
        repository_data: RepositoryData,
    ) -> AnalysisLimits:
        """Expose retrieval limits without exposing raw tool state."""
        return AnalysisLimits(
            file_count_retrieved=len(repository_data.file_tree),
            file_tree_truncated=repository_data.file_tree_truncated,
            readme_available=repository_data.readme.available,
            readme_truncated=repository_data.readme.truncated,
            redacted_secret_count=repository_data.readme.secrets_redacted,
        )

    def _build_recommendations(
        self,
        *,
        repository_result: dict[str, Any],
        documentation_result: dict[str, Any],
    ) -> list[UnifiedRecommendation]:
        """Normalize and deduplicate recommendations from current analyzers."""
        recommendations: list[UnifiedRecommendation] = []
        seen_keys: set[str] = set()

        missing_artifacts = repository_result.get("missing_artifacts", [])

        if isinstance(missing_artifacts, list):
            for item in missing_artifacts:
                if not isinstance(item, dict):
                    continue

                artifact = str(
                    item.get("artifact", "Repository artifact")
                ).strip()
                action = str(item.get("reason", "")).strip()

                if not action:
                    continue

                self._append_recommendation(
                    target=recommendations,
                    seen_keys=seen_keys,
                    category="repository_structure",
                    artifact=artifact,
                    priority=self._normalize_priority(
                        item.get("priority")
                    ),
                    recommendation=action,
                    rationale=(
                        "Identified from deterministic repository structure "
                        "analysis."
                    ),
                    source="repository_structure",
                )

        documentation_recommendations = documentation_result.get(
            "recommendations",
            [],
        )

        if isinstance(documentation_recommendations, list):
            for item in documentation_recommendations:
                if not isinstance(item, dict):
                    continue

                artifact = str(
                    item.get("artifact", "Documentation")
                ).strip()
                action = str(item.get("recommendation", "")).strip()
                rationale = str(item.get("rationale", "")).strip()

                if not action:
                    continue

                self._append_recommendation(
                    target=recommendations,
                    seen_keys=seen_keys,
                    category="documentation",
                    artifact=artifact,
                    priority=self._normalize_priority(
                        item.get("priority")
                    ),
                    recommendation=action,
                    rationale=rationale,
                    source="documentation",
                )

        priority_order = {
            Priority.HIGH: 0,
            Priority.MEDIUM: 1,
            Priority.LOW: 2,
        }

        return sorted(
            recommendations,
            key=lambda item: (
                priority_order[item.priority],
                item.category,
                item.artifact.lower(),
            ),
        )

    def _append_recommendation(
        self,
        *,
        target: list[UnifiedRecommendation],
        seen_keys: set[str],
        category: str,
        artifact: str,
        priority: Priority,
        recommendation: str,
        rationale: str,
        source: str,
    ) -> None:
        """Append a recommendation when an equivalent one is not present."""
        normalized_key = (
            f"{artifact.lower()}::{recommendation.lower().strip()}"
        )

        if normalized_key in seen_keys:
            return

        recommendation_hash = hashlib.sha256(
            normalized_key.encode("utf-8")
        ).hexdigest()[:12]

        target.append(
            UnifiedRecommendation(
                recommendation_id=f"REC-{recommendation_hash.upper()}",
                category=category,
                artifact=artifact,
                priority=priority,
                recommendation=recommendation,
                rationale=rationale,
                sources=[source],
            )
        )

        seen_keys.add(normalized_key)

    @staticmethod
    def _normalize_priority(value: object) -> Priority:
        """Convert analyzer priority values into one enum."""
        normalized = str(value or "medium").lower()

        if normalized == Priority.HIGH.value:
            return Priority.HIGH

        if normalized == Priority.LOW.value:
            return Priority.LOW

        return Priority.MEDIUM

    @staticmethod
    def _merge_limitations(
        *,
        repository_data: RepositoryData,
        repository_result: dict[str, Any],
        documentation_result: dict[str, Any],
    ) -> list[str]:
        """Combine limitations without duplicates."""
        limitations: list[str] = []

        candidate_groups = [
            repository_data.limitations,
            repository_result.get("limitations", []),
            documentation_result.get("limitations", []),
        ]

        for group in candidate_groups:
            if not isinstance(group, list):
                continue

            for limitation in group:
                if (
                    isinstance(limitation, str)
                    and limitation
                    and limitation not in limitations
                ):
                    limitations.append(limitation)

        return limitations

    def _calculate_preliminary_score(
        self,
        *,
        repository_result: dict[str, Any],
        documentation_result: dict[str, Any],
    ) -> RepositoryHealthScore:
        """Calculate a temporary deterministic score for Phase 1.

        This must later be replaced by the versioned commercial scoring engine.
        """
        missing_artifacts = repository_result.get("missing_artifacts", [])
        assessments = documentation_result.get("assessments", [])

        structure_deduction = 0

        if isinstance(missing_artifacts, list):
            for item in missing_artifacts:
                if not isinstance(item, dict):
                    continue

                priority = self._normalize_priority(item.get("priority"))

                structure_deduction += {
                    Priority.HIGH: 20,
                    Priority.MEDIUM: 10,
                    Priority.LOW: 5,
                }[priority]

        structure_score = max(0, 100 - structure_deduction)

        documentation_deduction = 0
        documentation_findings = 0

        if isinstance(assessments, list):
            for assessment in assessments:
                if not isinstance(assessment, dict):
                    continue

                status = str(
                    assessment.get("status", "unavailable")
                ).lower()

                if status == "missing":
                    documentation_deduction += 20
                    documentation_findings += 1
                elif status == "partial":
                    documentation_deduction += 10
                    documentation_findings += 1

        documentation_score = max(0, 100 - documentation_deduction)

        overall_score = round(
            (structure_score * 0.5) + (documentation_score * 0.5)
        )

        return RepositoryHealthScore(
            overall_score=overall_score,
            categories=[
                CategoryScore(
                    category="repository_structure",
                    score=structure_score,
                    finding_count=(
                        len(missing_artifacts)
                        if isinstance(missing_artifacts, list)
                        else 0
                    ),
                    scoring_note=(
                        "Based on missing baseline repository artifacts."
                    ),
                ),
                CategoryScore(
                    category="documentation",
                    score=documentation_score,
                    finding_count=documentation_findings,
                    scoring_note=(
                        "Based on current README and standard documentation "
                        "artifact assessments."
                    ),
                ),
            ],
        )