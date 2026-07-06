"""Temporary Phase 4 ADK root-agent entry point."""

from app.agents.documentation_agent import documentation_agent

# In Phase 5, the Coordinator Agent becomes root_agent and delegates to both
# Repository Analysis Agent and Documentation Analysis Agent.
root_agent = documentation_agent