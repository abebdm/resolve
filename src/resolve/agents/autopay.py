"""The auto-payer: an agent-side helper that pays mana costs (design.md §6, plan M2.5)."""

from __future__ import annotations

from resolve.agents.base import Agent
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.engine.view import PlayerView


class AutoPayAgent:
    """Answers the payment decisions itself and delegates the rest to ``inner`` (stub)."""

    def __init__(self, inner: Agent) -> None:
        self.inner = inner

    def decide(self, view: PlayerView, request: DecisionRequest) -> DecisionAnswer:
        return self.inner.decide(view, request)
