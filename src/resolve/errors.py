"""Exceptions raised by the engine.

What each one means for the game state (design.md §3):

- ``InvalidAnswer``: an answer was rejected. Nothing was changed; the same decision is still
  pending and the agent may answer again.
- ``NotImplementedRule``: the game needed a rule the engine doesn't implement yet. The state is
  left as it was when the gap was reached and must not be played further.
- ``EngineError``: an engine bug or a misuse of the API. The state must not be played further.
- ``DeckError``: a deck can't be used to start a game.
"""

from __future__ import annotations

from resolve.citations import is_rule_reference


class NotImplementedRule(Exception):
    """A rule the engine doesn't implement yet was needed, so the game stops loudly.

    The message is ``"<CR number>: <what>"``, for example
    ``NotImplementedRule("103.5: opening hands and mulligans")``. A malformed message raises
    ``ValueError``, so every gap names the rule it is about. ``tools/gaps.py`` lists all gaps.
    """

    def __init__(self, message: str) -> None:
        rule, separator, what = message.partition(": ")
        if not separator or not what.strip() or not is_rule_reference(rule):
            raise ValueError(
                f"NotImplementedRule message must be '<CR number>: <what>', got {message!r}"
            )
        super().__init__(message)
        self.rule = rule
        self.what = what


class EngineError(Exception):
    """The engine is in a state that should be impossible, or its API was misused."""


class InvalidAnswer(ValueError):
    """A decision answer was rejected; the state is unchanged (design.md §6)."""


class DeckError(ValueError):
    """A deck can't be used to start a game (unknown or unimplemented cards, bad setup)."""
