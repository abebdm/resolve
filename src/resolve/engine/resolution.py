"""Resolving the top object of the stack (608).

``ResolveTopOfStack`` runs when all players pass in succession with objects on the stack (117.4,
405.5): the top (last-added) object resolves (608.1).

- A permanent spell (110.4: an artifact, battle, creature, enchantment or planeswalker spell)
  becomes a permanent on the battlefield under its controller's control (608.3a), keeping how
  it was cast (400.7d). Permanent spells with targets (Auras, bestow, mutate: 608.3b-d) can't be
  cast yet (601.2c, M4). Nothing can stop a permanent from entering yet (608.3e, M6).
- An instant or sorcery follows its instructions (608.2c), then goes where
  ``defaults.resolved_spell_destination`` says (608.2n). Spell abilities arrive in M2.6, so
  resolving one is a gap until then.

The priority task gives the active player priority afterwards (117.3b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.effects.characteristics import characteristics
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import PermanentSpellResolved
from resolve.tasks import Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.state.game import GameState


@dataclass(slots=True)
class ResolveTopOfStack(Task):
    """The top object of the stack resolves (608.1, 405.5)."""

    def run(self, state: GameState) -> TaskResult:
        if not state.stack:
            raise EngineError("there is nothing on the stack to resolve")
        top = state.stack[-1]
        obj = state.objects[top]
        if obj.spell is None:
            raise EngineError(f"object {top} on the stack isn't a spell")
        types = characteristics(state, top).card_types
        if CardType.INSTANT in types or CardType.SORCERY in types:
            raise NotImplementedRule(
                "608.2c: following an instant or sorcery spell's instructions (M2.6)"
            )
        resolved = PermanentSpellResolved(spell=top, rules=("608.3a", "400.7"))
        return Push((ApplyEvents((resolved,)),))
