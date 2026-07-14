"""Coordinator Agent using the canonical repository-analysis service."""

from __future__ import annotations

import logging

from google.adk import Agent

from app.config.settings import get_settings
from app.prompts.coordinator_prompt import COORDINATOR_AGENT_INSTRUCTION
from app.tools.unified_analysis_tool import analyze_repository

LOGGER = logging.getLogger(__name__)

settings = get_settings()

try:
    coordinator_agent = Agent(
        name="github_repository_optimizer_coordinator",
        model=settings.gemini_model,
        description=(
            "Coordinates evidence-based analysis of public GitHub "
            "repositories through the canonical application service."
        ),
        instruction=COORDINATOR_AGENT_INSTRUCTION,
        tools=[analyze_repository],
    )

    LOGGER.info(
        "coordinator_agent_initialized",
        extra={
            "agent_name": coordinator_agent.name,
            "tool_names": ["analyze_repository"],
        },
    )

except Exception as error:
    LOGGER.exception(
        "coordinator_agent_initialization_failed",
        extra={"error_type": type(error).__name__},
    )

    raise RuntimeError(
        "Coordinator Agent could not be initialized. "
        "Check ADK configuration and unified analysis tool imports."
    ) from error