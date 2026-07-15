"""Tests for repository context retrieval orchestration."""

from unittest.mock import Mock, patch

from app.services.repository_context_service import (
    RepositoryContextService,
)


@patch(
    "app.services.repository_context_service.GitHubRepositoryClient"
)
def test_build_context_fetches_repository_once(
    client_class: Mock,
) -> None:
    """One context construction should perform one repository fetch."""
    expected_context = Mock()

    expected_context.repository.owner = "example"
    expected_context.repository.repository = "repository"
    expected_context.file_tree = []

    client = client_class.return_value
    client.fetch_repository.return_value = expected_context

    service = RepositoryContextService()

    result = service.build_context(
        "https://github.com/example/repository"
    )

    assert result is expected_context

    client.fetch_repository.assert_called_once_with(
        "https://github.com/example/repository"
    )
    client.close.assert_called_once()