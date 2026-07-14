"""Repository-context retrieval service.

This service is the only application-layer component that should retrieve
GitHub repository data during one analysis execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.tools.github_tool import (
    GitHubRepositoryClient,
    GitHubToolError,
    RepositoryData,
)

LOGGER = logging.getLogger(__name__)


class RepositoryContextServiceError(RuntimeError):
    """Raised when repository context cannot be constructed safely."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass
class RepositoryContextService:
    """Fetch and validate one shared repository context."""

    def build_context(self, repository_url: str) -> RepositoryData:
        """Retrieve repository data exactly once.

        Args:
            repository_url: Public GitHub repository URL.

        Returns:
            Validated RepositoryData from the GitHub gateway.

        Raises:
            RepositoryContextServiceError: When retrieval fails.
        """
        client = GitHubRepositoryClient()

        try:
            LOGGER.info(
                "repository_context_build_started",
                extra={"repository_url": repository_url},
            )

            context = client.fetch_repository(repository_url)

            LOGGER.info(
                "repository_context_build_completed",
                extra={
                    "owner": context.repository.owner,
                    "repository": context.repository.repository,
                    "tree_entries": len(context.file_tree),
                },
            )

            return context

        except GitHubToolError as error:
            LOGGER.warning(
                "repository_context_build_failed",
                extra={"error_type": type(error).__name__},
            )

            raise RepositoryContextServiceError(
                error_code=self._error_code_for(error),
                message=str(error),
            ) from error

        except Exception as error:
            LOGGER.exception(
                "repository_context_unexpected_failure",
                extra={"error_type": type(error).__name__},
            )

            raise RepositoryContextServiceError(
                error_code="repository_context_failed",
                message=(
                    "The repository context could not be created safely."
                ),
            ) from error

        finally:
            client.close()

    @staticmethod
    def _error_code_for(error: GitHubToolError) -> str:
        """Convert GitHub domain exceptions into application error codes."""
        error_name = type(error).__name__

        mapping = {
            "InvalidGitHubUrlError": "invalid_github_url",
            "PrivateRepositoryBlockedError": (
                "private_repository_not_supported"
            ),
            "RepositoryNotFoundError": "repository_not_found",
            "GitHubRateLimitError": "github_rate_limit",
            "GitHubApiError": "github_api_error",
        }

        return mapping.get(error_name, "github_repository_error")