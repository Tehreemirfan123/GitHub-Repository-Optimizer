"""Tests for report recommendation normalization."""

from app.schemas.analysis import Priority
from app.services.report_service import ReportService


def test_recommendations_are_deduplicated() -> None:
    """Equivalent recommendations should appear once."""
    service = ReportService()

    recommendations = service._build_recommendations(
        repository_result={
            "missing_artifacts": [
                {
                    "artifact": "README.md",
                    "reason": "Add a project README.",
                    "priority": "high",
                },
                {
                    "artifact": "README.md",
                    "reason": "Add a project README.",
                    "priority": "high",
                },
            ]
        },
        documentation_result={"recommendations": []},
    )

    assert len(recommendations) == 1
    assert recommendations[0].priority == Priority.HIGH