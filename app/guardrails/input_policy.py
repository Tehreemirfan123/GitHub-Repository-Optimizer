"""Input validation policy for public GitHub repository URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


class InputPolicyError(ValueError):
    """Raised when repository input violates the application safety policy."""


class PublicRepositoryReference(BaseModel):
    """Validated reference to a public GitHub repository."""

    model_config = ConfigDict(str_strip_whitespace=True)

    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    normalized_url: str = Field(
        pattern=r"^https://github\.com/[^/]+/[^/]+$"
    )


_GITHUB_OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)

_GITHUB_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9._-]{1,100}$"
)


def validate_public_github_repository_url(
    repository_url: str,
) -> PublicRepositoryReference:
    """Validate and normalize a standard public GitHub repository URL.

    Accepted examples:
        https://github.com/owner/repository
        https://github.com/owner/repository/
        https://github.com/owner/repository.git

    Rejected examples:
        http://github.com/owner/repository
        https://github.com/owner/repository/tree/main
        https://user:password@github.com/owner/repository
        https://gitlab.com/owner/repository
    """
    raw_url = repository_url.strip()

    if not raw_url:
        raise InputPolicyError("GitHub repository URL cannot be empty.")

    parsed_url = urlparse(raw_url)

    if parsed_url.scheme != "https":
        raise InputPolicyError(
            "Repository URL must use HTTPS. "
            "Example: https://github.com/owner/repository"
        )

    hostname = (parsed_url.hostname or "").lower()

    if hostname not in {"github.com", "www.github.com"}:
        raise InputPolicyError(
            "Only public github.com repository URLs are supported."
        )

    if parsed_url.username or parsed_url.password or parsed_url.port:
        raise InputPolicyError(
            "Repository URL must not include credentials or a custom port."
        )

    path_parts = [
        item
        for item in parsed_url.path.strip("/").split("/")
        if item
    ]

    if len(path_parts) != 2:
        raise InputPolicyError(
            "Repository URL must follow this format: "
            "https://github.com/owner/repository"
        )

    owner, repository = path_parts

    if repository.lower().endswith(".git"):
        repository = repository[:-4]

    if not _GITHUB_OWNER_PATTERN.fullmatch(owner):
        raise InputPolicyError(
            "The GitHub repository owner format is invalid."
        )

    if not _GITHUB_REPOSITORY_PATTERN.fullmatch(repository):
        raise InputPolicyError(
            "The GitHub repository name format is invalid."
        )

    return PublicRepositoryReference(
        owner=owner,
        repository=repository,
        normalized_url=f"https://github.com/{owner}/{repository}",
    )