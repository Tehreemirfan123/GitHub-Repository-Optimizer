"""Basic secret masking for repository content returned to AI agents."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class SecretRedactor:
    """Masks common token and credential patterns from text and JSON-like data."""

    _patterns: tuple[re.Pattern[str], ...] = (
        # GitHub tokens.
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),

        # Google API keys.
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),

        # OpenAI-style API keys.
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),

        # AWS access key IDs.
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),

        # Authorization headers.
        re.compile(
            r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
        ),

        # Common environment-variable assignments.
        re.compile(
            r"(?im)\b("
            r"GITHUB_TOKEN|"
            r"GOOGLE_API_KEY|"
            r"OPENAI_API_KEY|"
            r"API_KEY|"
            r"SECRET_KEY|"
            r"ACCESS_TOKEN|"
            r"PASSWORD"
            r")\s*=\s*([^\s'\"`]{8,})"
        ),
    )

    def redact_text(self, text: str) -> tuple[str, int]:
        """Return masked text and the number of replacements performed."""
        redacted_text = text
        replacements = 0

        for pattern in self._patterns:
            if pattern.pattern.startswith("(?im)"):
                redacted_text, count = pattern.subn(
                    lambda match: f"{match.group(1)}=[REDACTED]",
                    redacted_text,
                )
            elif "(Bearer)" in pattern.pattern:
                redacted_text, count = pattern.subn(
                    r"\1 [REDACTED]",
                    redacted_text,
                )
            else:
                redacted_text, count = pattern.subn(
                    "[REDACTED]",
                    redacted_text,
                )

            replacements += count

        return redacted_text, replacements

    def redact_data(self, value: Any) -> Any:
        """Recursively redact strings inside JSON-compatible data."""
        if isinstance(value, str):
            redacted_value, _ = self.redact_text(value)
            return redacted_value

        if isinstance(value, Mapping):
            return {
                str(key): self.redact_data(item)
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [self.redact_data(item) for item in value]

        if isinstance(value, tuple):
            return tuple(self.redact_data(item) for item in value)

        return value