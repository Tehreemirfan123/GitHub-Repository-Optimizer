"""Canonical application service for repository analysis."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.agents.documentation_agent import (
    analyze_documentation_context,
)
from app.agents.repository_agent import analyze_repository_context
from app.schemas.analysis import (
    AgentExecutionStatus,
    AnalysisError,
    AnalysisProfile,
    AnalysisStatus,
    ComponentResult,
    RepositoryAnalysisReport,
)
from app.services.report_service import ReportService
from app.services.repository_context_service import (
    RepositoryContextService,
    RepositoryContextServiceError,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class AnalysisService:
    """Coordinate one complete repository-analysis execution."""

    context_service: RepositoryContextService = field(
        default_factory=RepositoryContextService
    )
    report_service: ReportService = field(default_factory=ReportService)

    async def analyze_repository(
        self,
        repository_url: str,
        analysis_profile: str = AnalysisProfile.STANDARD.value,
    ) -> RepositoryAnalysisReport:
        """Run one canonical analysis pipeline.

        GitHub retrieval occurs exactly once. All analyzers receive the same
        immutable validated RepositoryData instance.
        """
        try:
            profile = AnalysisProfile(analysis_profile)
        except ValueError:
            return self._failed_report(
                profile=AnalysisProfile.STANDARD,
                error_code="invalid_analysis_profile",
                message=(
                    f"Unsupported analysis profile: {analysis_profile}."
                ),
                component="analysis_service",
            )

        LOGGER.info(
            "repository_analysis_started",
            extra={
                "repository_url": repository_url,
                "analysis_profile": profile.value,
            },
        )

        try:
            repository_data = await asyncio.to_thread(
                self.context_service.build_context,
                repository_url,
            )
        except RepositoryContextServiceError as error:
            return self._failed_report(
                profile=profile,
                error_code=error.error_code,
                message=error.message,
                component="repository_context",
            )

        components: list[ComponentResult] = []
        errors: list[AnalysisError] = []

        repository_result: dict = {}
        documentation_result: dict = {}

        try:
            repository_result = await asyncio.to_thread(
                analyze_repository_context,
                repository_data,
            )

            components.append(
                ComponentResult(
                    component_name="repository_structure",
                    status=AgentExecutionStatus.COMPLETED,
                    result=repository_result,
                )
            )
        except Exception as error:
            LOGGER.exception(
                "repository_structure_analysis_failed",
                extra={"error_type": type(error).__name__},
            )

            safe_error = AnalysisError(
                error_code="repository_structure_analysis_failed",
                message=(
                    "Repository structure analysis could not be completed."
                ),
                component="repository_structure",
            )

            errors.append(safe_error)
            components.append(
                ComponentResult(
                    component_name="repository_structure",
                    status=AgentExecutionStatus.FAILED,
                    error=safe_error,
                )
            )

        try:
            documentation_result = await asyncio.to_thread(
                analyze_documentation_context,
                repository_data,
            )

            components.append(
                ComponentResult(
                    component_name="documentation",
                    status=AgentExecutionStatus.COMPLETED,
                    result=documentation_result,
                )
            )
        except Exception as error:
            LOGGER.exception(
                "documentation_analysis_failed",
                extra={"error_type": type(error).__name__},
            )

            safe_error = AnalysisError(
                error_code="documentation_analysis_failed",
                message=(
                    "Documentation analysis could not be completed."
                ),
                component="documentation",
            )

            errors.append(safe_error)
            components.append(
                ComponentResult(
                    component_name="documentation",
                    status=AgentExecutionStatus.FAILED,
                    error=safe_error,
                )
            )

        if not repository_result and not documentation_result:
            report = self._failed_report(
                profile=profile,
                error_code="all_analysis_components_failed",
                message="No analysis component completed successfully.",
                component="analysis_service",
            )
            report.components = components
            report.errors.extend(errors)
            return report

        report = self.report_service.build_report(
            repository_data=repository_data,
            analysis_profile=profile,
            repository_result=repository_result,
            documentation_result=documentation_result,
            components=components,
        )

        if errors:
            report.status = AnalysisStatus.PARTIALLY_COMPLETED
            report.errors = errors

        LOGGER.info(
            "repository_analysis_completed",
            extra={
                "analysis_id": report.analysis_id,
                "status": report.status.value,
                "recommendation_count": len(report.recommendations),
            },
        )

        return report

    def analyze_repository_sync(
        self,
        repository_url: str,
        analysis_profile: str = AnalysisProfile.STANDARD.value,
    ) -> RepositoryAnalysisReport:
        """Synchronous adapter for Streamlit, ADK tools, and simple CLI use."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.analyze_repository(
                    repository_url=repository_url,
                    analysis_profile=analysis_profile,
                )
            )

        raise RuntimeError(
            "analyze_repository_sync cannot run inside an active event loop. "
            "Use await analyze_repository(...) instead."
        )

    @staticmethod
    def _failed_report(
        *,
        profile: AnalysisProfile,
        error_code: str,
        message: str,
        component: str,
    ) -> RepositoryAnalysisReport:
        """Create a safe failed result without raising to presentation layers."""
        error = AnalysisError(
            error_code=error_code,
            message=message,
            component=component,
        )

        return RepositoryAnalysisReport(
            analysis_profile=profile,
            status=AnalysisStatus.FAILED,
            errors=[error],
        )


analysis_service = AnalysisService()