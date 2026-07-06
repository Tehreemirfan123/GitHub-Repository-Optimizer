"""Read-only GitHub repository retrieval tool.

Responsibilities:
- Validate a public GitHub repository URL.
- Fetch repository metadata.
- Fetch README content when available.
- Fetch a bounded recursive file tree.

This module does not analyze repository quality. Analysis begins in later phases.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, HttpUrl


LOGGER = logging.getLogger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_README_CHARACTERS = 50_000
MAX_TREE_ENTRIES = 1_000


class GitHubToolError(RuntimeError):
    """Base exception for safe GitHub tool failures."""


class InvalidGitHubUrlError(GitHubToolError):
    """Raised when a supplied GitHub repository URL is invalid."""


class RepositoryNotFoundError(GitHubToolError):
    """Raised when a public repository cannot be found."""


class GitHubRateLimitError(GitHubToolError):
    """Raised when GitHub API rate limits block the request."""


class GitHubApiError(GitHubToolError):
    """Raised when GitHub returns an unexpected response."""


class RepositoryReference(BaseModel):
    """Validated and normalized public GitHub repository reference."""

    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    url: HttpUrl


class RepositoryMetadata(BaseModel):
    """Public metadata returned by GitHub for one repository."""

    name: str
    owner: str
    description: str | None = None
    default_branch: str
    language: str | None = None
    stars: int = Field(ge=0)
    forks: int = Field(ge=0)
    topics: list[str] = Field(default_factory=list)
    url: HttpUrl


class ReadmeData(BaseModel):
    """README information returned by GitHub."""

    available: bool
    path: str | None = None
    content: str | None = None
    truncated: bool = False


class FileTreeEntry(BaseModel):
    """One file or directory entry from a GitHub recursive tree response."""

    path: str
    type: str
    size_bytes: int | None = None


class RepositoryData(BaseModel):
    """Complete Phase 2 repository retrieval result."""

    success: bool = True
    repository: RepositoryReference
    metadata: RepositoryMetadata
    readme: ReadmeData
    file_tree: list[FileTreeEntry]
    file_tree_truncated: bool = False
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class GitHubClientConfig:
    """Configuration for the read-only GitHub HTTP client."""

    api_base_url: str = GITHUB_API_BASE_URL
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
    max_readme_characters: int = MAX_README_CHARACTERS
    max_tree_entries: int = MAX_TREE_ENTRIES


def parse_github_repository_url(repository_url: str) -> RepositoryReference:
    """Validate and normalize a GitHub repository URL.

    Accepted examples:
    - https://github.com/owner/repository
    - https://github.com/owner/repository/
    - https://github.com/owner/repository.git

    Args:
        repository_url: Public GitHub repository URL.

    Returns:
        Validated repository reference.

    Raises:
        InvalidGitHubUrlError: If the URL is unsupported or malformed.
    """
    raw_url = repository_url.strip()

    if not raw_url:
        raise InvalidGitHubUrlError("GitHub repository URL cannot be empty.")

    parsed = urlparse(raw_url)

    if parsed.scheme != "https":
        raise InvalidGitHubUrlError(
            "Use an HTTPS GitHub URL, for example: "
            "https://github.com/owner/repository"
        )

    if parsed.hostname not in {"github.com", "www.github.com"}:
        raise InvalidGitHubUrlError(
            "Only github.com repository URLs are supported."
        )

    if parsed.username or parsed.password or parsed.port:
        raise InvalidGitHubUrlError(
            "Repository URLs must not contain credentials or custom ports."
        )

    parts = [part for part in parsed.path.strip("/").split("/") if part]

    if len(parts) != 2:
        raise InvalidGitHubUrlError(
            "Repository URL must follow: https://github.com/owner/repository"
        )

    owner, repository = parts
    repository = repository.removesuffix(".git")

    if not owner or not repository:
        raise InvalidGitHubUrlError(
            "Repository owner and repository name are required."
        )

    return RepositoryReference(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


class GitHubRepositoryClient:
    """Read-only client for GitHub public repository data."""

    def __init__(
        self,
        config: GitHubClientConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config or GitHubClientConfig()
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self._config.api_base_url,
            timeout=self._config.timeout_seconds,
            follow_redirects=False,
        )

    def close(self) -> None:
        """Close the internally-created HTTP client."""
        if self._owns_client:
            self._client.close()

    def fetch_repository(self, repository_url: str) -> RepositoryData:
        """Fetch public repository metadata, README, and file tree.

        Args:
            repository_url: Public GitHub repository URL.

        Returns:
            Structured repository data with no analysis or recommendations.
        """
        reference = parse_github_repository_url(repository_url)

        LOGGER.info(
            "github_repository_fetch_started",
            extra={
                "owner": reference.owner,
                "repository": reference.repository,
            },
        )

        metadata_payload = self._get_json(
            f"/repos/{reference.owner}/{reference.repository}"
        )

        if bool(metadata_payload.get("private")):
            raise GitHubApiError(
                "Private repositories are not supported in this phase."
            )

        metadata = self._build_metadata(metadata_payload)
        readme, readme_limitations = self._fetch_readme(reference)
        file_tree, tree_truncated, tree_limitations = self._fetch_file_tree(
            reference=reference,
            default_branch=metadata.default_branch,
        )

        result = RepositoryData(
            repository=reference,
            metadata=metadata,
            readme=readme,
            file_tree=file_tree,
            file_tree_truncated=tree_truncated,
            limitations=[*readme_limitations, *tree_limitations],
        )

        LOGGER.info(
            "github_repository_fetch_completed",
            extra={
                "owner": reference.owner,
                "repository": reference.repository,
                "readme_available": readme.available,
                "tree_entries": len(file_tree),
                "tree_truncated": tree_truncated,
            },
        )

        return result

    def _build_headers(self) -> dict[str, str]:
        """Build GitHub REST API headers without exposing tokens in logs."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "github-repository-optimizer-agent",
        }

        github_token = os.getenv("GITHUB_TOKEN", "").strip()
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        return headers

    def _get_json(self, endpoint: str) -> dict[str, Any]:
        """Execute a safe GET request and return a JSON object."""
        try:
            response = self._client.get(
                endpoint,
                headers=self._build_headers(),
            )
        except httpx.TimeoutException as error:
            raise GitHubApiError(
                "GitHub did not respond before the configured timeout."
            ) from error
        except httpx.RequestError as error:
            raise GitHubApiError(
                "Could not connect to the GitHub REST API."
            ) from error

        self._raise_for_http_error(response)

        try:
            payload = response.json()
        except ValueError as error:
            raise GitHubApiError(
                "GitHub returned an invalid JSON response."
            ) from error

        if not isinstance(payload, dict):
            raise GitHubApiError(
                "GitHub returned an unexpected response format."
            )

        return payload

    def _raise_for_http_error(self, response: httpx.Response) -> None:
        """Map GitHub HTTP errors to safe domain exceptions."""
        if response.is_success:
            return

        remaining = response.headers.get("X-RateLimit-Remaining")

        if response.status_code == 403 and remaining == "0":
            raise GitHubRateLimitError(
                "GitHub API rate limit reached. Add GITHUB_TOKEN to app/.env "
                "or try again later."
            )

        if response.status_code == 404:
            raise RepositoryNotFoundError(
                "Repository was not found or is not publicly accessible."
            )

        if response.status_code in {401, 403}:
            raise GitHubApiError(
                "GitHub denied access to this repository."
            )

        raise GitHubApiError(
            f"GitHub API request failed with HTTP {response.status_code}."
        )

    def _build_metadata(self, payload: dict[str, Any]) -> RepositoryMetadata:
        """Convert GitHub repository metadata into a validated model."""
        owner_payload = payload.get("owner")

        if not isinstance(owner_payload, dict):
            raise GitHubApiError("GitHub response did not include an owner.")

        topics = payload.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        try:
            return RepositoryMetadata(
                name=str(payload["name"]),
                owner=str(owner_payload["login"]),
                description=payload.get("description"),
                default_branch=str(payload["default_branch"]),
                language=payload.get("language"),
                stars=int(payload.get("stargazers_count", 0)),
                forks=int(payload.get("forks_count", 0)),
                topics=[str(topic) for topic in topics],
                url=payload["html_url"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise GitHubApiError(
                "GitHub repository metadata was incomplete."
            ) from error

    def _fetch_readme(
        self,
        reference: RepositoryReference,
    ) -> tuple[ReadmeData, list[str]]:
        """Fetch README content. Missing README is not a fatal error."""
        endpoint = f"/repos/{reference.owner}/{reference.repository}/readme"

        try:
            payload = self._get_json(endpoint)
        except RepositoryNotFoundError:
            return (
                ReadmeData(available=False),
                ["README was not available through the GitHub REST API."],
            )

        encoded_content = payload.get("content")
        encoding = payload.get("encoding")

        if not isinstance(encoded_content, str) or encoding != "base64":
            return (
                ReadmeData(
                    available=True,
                    path=payload.get("path"),
                    content=None,
                ),
                ["README metadata was available, but content could not be decoded."],
            )

        try:
            decoded = base64.b64decode(
                encoded_content.encode("utf-8"),
                validate=False,
            ).decode("utf-8", errors="replace")
        except (UnicodeEncodeError, binascii.Error) as error:
            raise GitHubApiError(
                "README content could not be decoded safely."
            ) from error

        truncated = len(decoded) > self._config.max_readme_characters
        if truncated:
            decoded = decoded[: self._config.max_readme_characters]

        limitations: list[str] = []
        if truncated:
            limitations.append(
                "README was truncated to the configured safety limit."
            )

        return (
            ReadmeData(
                available=True,
                path=payload.get("path"),
                content=decoded,
                truncated=truncated,
            ),
            limitations,
        )

    def _fetch_file_tree(
        self,
        reference: RepositoryReference,
        default_branch: str,
    ) -> tuple[list[FileTreeEntry], bool, list[str]]:
        """Fetch a bounded recursive Git tree for the default branch."""
        endpoint = (
            f"/repos/{reference.owner}/{reference.repository}"
            f"/git/trees/{default_branch}?recursive=1"
        )

        payload = self._get_json(endpoint)
        raw_tree = payload.get("tree", [])

        if not isinstance(raw_tree, list):
            raise GitHubApiError(
                "GitHub file tree response was invalid."
            )

        entries: list[FileTreeEntry] = []

        for item in raw_tree[: self._config.max_tree_entries]:
            if not isinstance(item, dict):
                continue

            path = item.get("path")
            entry_type = item.get("type")

            if not isinstance(path, str) or not isinstance(entry_type, str):
                continue

            size = item.get("size")
            entries.append(
                FileTreeEntry(
                    path=path,
                    type=entry_type,
                    size_bytes=size if isinstance(size, int) else None,
                )
            )

        github_truncated = bool(payload.get("truncated", False))
        local_truncated = len(raw_tree) > self._config.max_tree_entries
        tree_truncated = github_truncated or local_truncated

        limitations: list[str] = []
        if github_truncated:
            limitations.append(
                "GitHub reported that the recursive file tree was truncated."
            )
        if local_truncated:
            limitations.append(
                "File tree was limited to the configured maximum entry count."
            )

        return entries, tree_truncated, limitations


def fetch_github_repository(repository_url: str) -> dict[str, Any]:
    """Fetch public GitHub repository data without analyzing it.

    Args:
        repository_url: A public HTTPS GitHub repository URL in this format:
            https://github.com/owner/repository

    Returns:
        A structured dictionary containing repository metadata, README content,
        file-tree entries, and safe limitations. Future ADK agents can register
        this typed function directly as a function tool.

    Examples:
        fetch_github_repository("https://github.com/google/adk-python")
    """
    client = GitHubRepositoryClient()

    try:
        result = client.fetch_repository(repository_url)
        return result.model_dump(mode="json")
    except InvalidGitHubUrlError as error:
        return {
            "success": False,
            "error_code": "invalid_github_url",
            "message": str(error),
        }
    except RepositoryNotFoundError as error:
        return {
            "success": False,
            "error_code": "repository_not_found",
            "message": str(error),
        }
    except GitHubRateLimitError as error:
        return {
            "success": False,
            "error_code": "github_rate_limit",
            "message": str(error),
        }
    except GitHubToolError as error:
        LOGGER.exception(
            "github_repository_fetch_failed",
            extra={"error_type": type(error).__name__},
        )
        return {
            "success": False,
            "error_code": "github_api_error",
            "message": str(error),
        }
    finally:
        client.close()