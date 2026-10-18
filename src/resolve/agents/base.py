"""The agent interface (design.md §3).

Humans (through a UI), AIs, network peers and scripted test agents are all agents. The driver
(``resolve.agents.driver.play``) gives an agent the deciding player's view and the pending
request, and submits whatever answer the agent returns; the engine validates it (design.md §6).
"""

from __future__ import annotations

from typing import Protocol

from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.engine.view import PlayerView


class Agent(Protocol):
    """Something that answers decisions for one or more players."""

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        """Answer ``request``, seeing only ``view`` (the deciding player's view)."""
        ...
