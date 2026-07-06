"""Root ADK agent entry point"""

from app.agents.coordinator_agent import coordinator_agent

# ADK discovers this variable when running:
# adk run app
# adk web
root_agent = coordinator_agent