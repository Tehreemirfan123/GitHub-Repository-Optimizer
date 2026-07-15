"""Tests for the asynchronous ADK analysis tool."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.analysis import (
    AnalysisProfile,
    AnalysisStatus,
    RepositoryAnalysisReport,
)
from app.tools.unified_analysis_tool import analyze_repository


@pytest.mark.asyncio
@patch(
    "app.tools.unified_analysis_tool.analysis_service.analyze_repository",
    new_callable=AsyncMock,
)
async def test_unified_tool_awaits_analysis_service(
    analyze_service: AsyncMock,
) -> None:
    """The ADK tool should use the canonical asynchronous service."""
    report = RepositoryAnalysisReport(
        analysis_profile=AnalysisProfile.STANDARD,
        status=AnalysisStatus.COMPLETED,
    )

    analyze_service.return_value = report

    result = await analyze_repository(
        repository_url="https://github.com/example/repository",
        analysis_profile="standard",
    )

    analyze_service.assert_awaited_once_with(
        repository_url="https://github.com/example/repository",
        analysis_profile="standard",
    )

    assert result["status"] == "completed"