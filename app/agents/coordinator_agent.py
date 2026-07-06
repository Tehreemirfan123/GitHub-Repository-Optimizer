"""Coordinator Agent.

The Coordinator becomes the root orchestration agent. It delegates repository
structure analysis and documentation analysis to specialist sub-agents, then
merges their returned findings into one final report.
"""

from __future__ import annotations

import logging

from google.adk import Agent

from app.agents.documentation_agent import documentation_agent
from app.agents.repository_agent import repository_agent
from app.config.settings import get_settings
from app.prompts.coordinator_prompt import COORDINATOR_AGENT_INSTRUCTION


LOGGER = logging.getLogger(__name__)

settings = get_settings()

try:
    coordinator_agent = Agent(
        name="github_repository_optimizer_coordinator",
        model=settings.gemini_model,
        description=(
            "Coordinates repository structure and documentation analysis "
            "for public GitHub repositories."
        ),
        instruction=COORDINATOR_AGENT_INSTRUCTION,
        sub_agents=[
            repository_agent,
            documentation_agent,
        ],
    )

    LOGGER.info(
        "coordinator_agent_initialized",
        extra={
            "agent_name": coordinator_agent.name,
            "sub_agents": [
                repository_agent.name,
                documentation_agent.name,
            ],
        },
    )

except Exception as error:
    LOGGER.exception(
        "coordinator_agent_initialization_failed",
        extra={"error_type": type(error).__name__},
    )

    raise RuntimeError(
        "Coordinator Agent could not be initialized. "
        "Check specialist-agent imports and ADK configuration."
    ) from error