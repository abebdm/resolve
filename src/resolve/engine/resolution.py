"""Resolving the top object of the stack (608).

``ResolveTopOfStack`` runs when all players pass in succession with objects on the stack (117.4,
405.5): the top (last-added) object resolves (608.1).

- A permanent spell (110.4: an artifact, battle, creature, enchantment or planeswalker spell)
  becomes a permanent on the battlefield under its controller's control (608.3a), keeping how
  it was cast (400.7d). Permanent spells with targets (Auras, bestow, mutate: 608.3b-d) can't be
  cast yet (601.2c, M4). Nothing can stop a permanent from entering yet (608.3e, M6).
- An instant or sorcery first checks its targets (608.2b, ``targeting.target_problem``): if it
  is targeted (115.6) and every target, for every instance of the word "target", is illegal, it
  doesn't resolve (``SpellDidNotResolve``: to its owner's graveyard, none of its effects).
  Otherwise ``ResolveSpell`` follows its instructions in the order written (608.2c): a modal
  spell's chosen modes in printed order, a mode chosen more than once that many times in sequence
  (700.2d), each mode's effects with the targets of its own instances; with only the legal
  targets (an illegal target isn't affected, and gives no information, 608.2b), then
  puts it where ``defaults.resolved_spell_destination`` says (608.2n), unless it already left
  the stack (608.2m).

The priority task gives the active player priority afterwards (117.3b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.base import Effect
from resolve.data.types import CardType
from resolve.effects.characteristics import characteristics
from resolve.effects.evaluation import Context, Timing
from resolve.errors import EngineError
from resolve.events.pipeline import ApplyEvents
from resolve.events.spells import PermanentSpellResolved, SpellDidNotResolve, SpellResolved
from resolve.rules import defaults, targeting
from resolve.rules.legality import Targeter
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import Target
from resolve.tasks import Push, Task, TaskResult
from resolve.values import Immutable

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
        if obj.spell is None or obj.controller is None:
            raise EngineError(f"object {top} on the stack isn't a spell")
        chars = characteristics(state, top)
        if not (chars.is_a(CardType.INSTANT) or chars.is_a(CardType.SORCERY)):
            resolved = PermanentSpellResolved(spell=top, rules=("608.3a", "400.7"))
            return Push((ApplyEvents((resolved,)),))
        ability = chars.spell_ability
        if ability is None:
            raise EngineError(f"{chars.name!r} has no spell ability: its definition is incomplete")
        record = obj.spell
        modes = ability.chosen(record.modes)
        if not modes:
            raise EngineError(f"spell {top} has no modes chosen (601.2b)")
        specs = ability.instances(record.modes)
        if len(record.targets) != len(specs):
            raise EngineError(f"spell {top} has no targets chosen for its text (601.2c)")
        # 608.2b: check the targets again; keep the legal ones.
        targeter = Targeter(obj.controller, top, chars)
        legal = tuple(
            tuple(t for t in chosen if targeting.target_problem(state, targeter, spec, t) is None)
            for spec, chosen in zip(specs, record.targets, strict=True)
        )
        if record.targeted and not any(legal):
            failed = SpellDidNotResolve(spell=top, rules=("608.2b",))
            return Push((ApplyEvents((failed,)),))
        # 608.2c, 700.2d: each chosen mode in turn, with the targets of its own instances.
        instructions: list[Instruction] = []
        for mode in modes:
            own, legal = legal[: len(mode.targets)], legal[len(mode.targets) :]
            instructions += [Instruction(effect, own) for effect in mode.effects]
        return Push((ResolveSpell(top, obj.controller, tuple(instructions)),))


@dataclass(frozen=True)
class Instruction(Immutable):
    """One effect of a resolving spell (608.2c) with the legal targets of the mode it is part of
    (608.2b), one tuple per instance of "target" in that mode: what its ``TargetRef`` indices
    refer to."""

    effect: Effect
    targets: tuple[tuple[Target, ...], ...]


@dataclass(slots=True)
class ResolveSpell(Task):
    """The instant or sorcery ``spell``, controlled by ``controller``, follows its instructions
    (608.2c): ``instructions`` in order (each chosen mode's effects in the order written, the
    modes in printed order, a repeated mode once per repetition, 700.2d), one at a time, each
    evaluated as it applies (608.2h) with its mode's targets still legal (608.2b). ``applied``
    counts the instructions done. Nothing is asked between them, so no player can act between
    modes. Then it is put where ``defaults.resolved_spell_destination`` says (608.2n), unless it
    has already left the stack: it still resolved fully (608.2m)."""

    spell: ObjectId
    controller: PlayerId
    instructions: tuple[Instruction, ...]
    applied: int = 0

    def run(self, state: GameState) -> TaskResult:
        while self.applied < len(self.instructions):
            instruction = self.instructions[self.applied]
            self.applied += 1
            context = Context(Timing.RESOLUTION, self.spell, self.controller, instruction.targets)
            tasks = instruction.effect.tasks(state, context)
            if tasks:
                return Push((*tasks, self))
        on_stack = self.spell in state.stack
        destination = defaults.resolved_spell_destination(state, self.spell) if on_stack else None
        rules = ("608.2n",) if on_stack else ("608.2m",)
        done = SpellResolved(spell=self.spell, destination=destination, rules=rules)
        return Push((ApplyEvents((done,)),))
