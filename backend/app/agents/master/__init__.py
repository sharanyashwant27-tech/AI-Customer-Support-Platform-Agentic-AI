"""Master Agent — understand request, delegate work, maintain context, manage memory."""

# Re-export graph facade; responsibilities documented for architecture alignment.
from app.agents.master.graph import MasterAgent, get_master_agent, reset_master_agent

__all__ = ["MasterAgent", "get_master_agent", "reset_master_agent"]

MASTER_RESPONSIBILITIES = [
    "Understand request",
    "Delegate work",
    "Maintain context",
    "Manage memory",
]
