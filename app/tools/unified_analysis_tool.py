"""Google ADK tool exposing the canonical application analysis workflow."""

from __future__ import annotations

from typing import Any

from app.services.analysis_service import analysis_service


def analyze_repository(
    repository_url: str,
    analysis_profile: str = "standard",
) -> dict[str, Any]:
    """Analyze a public GitHub repository through the canonical service.

    Args:
        repository_url: Complete public GitHub repository URL.
        analysis_profile: Analysis profile. Currently only ``standard``.

    Returns:
        Canonical validated repository analysis report.
    """
    report = analysis_service.analyze_repository_sync(
        repository_url=repository_url,
        analysis_profile=analysis_profile,
    )

    return report.model_dump(mode="json")