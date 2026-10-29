"""Agents: whatever answers decisions from a ``PlayerView`` (design.md §3).

- ``Agent``: the interface, one method ``decide(view, request) -> DecisionAnswer``.
- ``play``: the driver loop of design.md §3, asking each player's agent in turn.
- ``RandomAgent``: answers uniformly at random inside the answer space (fuzzing).
- ``CasterAgent`` (``resolve.agents.caster``): plays a land, then casts every spell it may (a
  fuzz seat, with the auto-payer ``resolve.agents.autopay.AutoPayAgent``).
- ``ScriptedAgent``: answers from a fixed script (tests and replays).
- ``TextAgent`` and the text renderer (``resolve.agents.text``): a human at a terminal.

Agents depend on the engine; the engine never imports agents. An agent sees only the immutable
``PlayerView`` and ``DecisionRequest`` it is given, never the game state.
"""

from resolve.agents.base import Agent
from resolve.agents.driver import play
from resolve.agents.random_agent import RandomAgent
from resolve.agents.scripted import Choose, ScriptedAgent, ScriptError, Step, choose

__all__ = [
    "Agent",
    "Choose",
    "RandomAgent",
    "ScriptError",
    "ScriptedAgent",
    "Step",
    "choose",
    "play",
]
