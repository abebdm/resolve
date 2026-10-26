"""Targets: what each instance of the word "target" may choose (115, 601.2c, design.md §17.11).

A ``TargetSpec`` is one instance of the word "target" in a spell's or ability's text: the kinds
of things it may choose (permanents through an ``ObjectFilter``, players through a
``PlayerFilter``, spells through a ``SpellFilter``) and how many (``minimum`` to ``maximum``).

- 115.2: only permanents are legal targets unless the text says otherwise, so an
  ``ObjectFilter`` only ever matches permanents; players and spells need their own filters.
- 115.4: "any target" is a creature, planeswalker or battle, or a player (``ANY_TARGET``).
- 115.3: one instance can't choose the same object or player twice (its choice is a subset), but
  separate instances may choose the same one (Decimate).

Whether a candidate is legal is decided by ``resolve.rules.targeting.target_problem`` alone, at
601.2c and again at 608.2b; the filters' ``matches`` are its second step. A modal spell's targets
are its chosen modes' (700.2c: ``SpellAbility.instances``); room is kept for targets that depend
on a cost paid (601.2c: kicker, M6) and for overload's "each" (M4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.primitives.refs import You
from resolve.data.types import CardType
from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.state.game import GameState
    from resolve.state.ids import ObjectId, PlayerId


@dataclass(frozen=True)
class ObjectFilter(Immutable):
    """Permanents (115.2) with at least one of ``card_types`` (none: any permanent), controlled
    by ``controller`` if given ("you control": the targeting spell's controller, 109.5)."""

    card_types: tuple[CardType, ...] = ()
    controller: You | None = None

    def matches(self, state: GameState, obj: ObjectId, you: PlayerId) -> bool:
        """Whether the permanent ``obj`` fits, judged for a spell or ability ``you`` control."""
        from resolve.effects.characteristics import characteristics

        if self.card_types:
            types = characteristics(state, obj).card_types
            if not any(card_type in types for card_type in self.card_types):
                return False
        return self.controller is None or state.object(obj).controller == you

    @property
    def text(self) -> str:
        """``"creature"``, ``"creature you control"``, ``"artifact or creature"``."""
        names = [card_type.value.lower() for card_type in self.card_types] or ["permanent"]
        noun = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
        return noun + (" you control" if self.controller is not None else "")


@dataclass(frozen=True)
class PlayerFilter(Immutable):
    """Players (115.1), or only opponents of the targeting spell's controller (102.2)."""

    opponents_only: bool = False

    def matches(self, state: GameState, player: PlayerId, you: PlayerId) -> bool:
        """Whether ``player`` fits, judged for a spell or ability ``you`` control."""
        return not self.opponents_only or player != you

    @property
    def text(self) -> str:
        """``"player"`` or ``"opponent"``."""
        return "opponent" if self.opponents_only else "player"


@dataclass(frozen=True)
class SpellFilter(Immutable):
    """Spells on the stack (115.2: an object that can't exist on the battlefield). Any spell so
    far; qualities ("target creature spell") join with their cards."""

    def matches(self, state: GameState, obj: ObjectId, you: PlayerId) -> bool:
        """Whether the spell ``obj`` fits."""
        return state.object(obj).spell is not None

    @property
    def text(self) -> str:
        """``"spell"``."""
        return "spell"


@dataclass(frozen=True)
class TargetSpec(Immutable):
    """One instance of the word "target" (115.1, 601.2c): from ``minimum`` to ``maximum``
    distinct choices (115.3) among the permanents ``objects`` allows, the players ``players``
    allows and the spells ``spells`` allows. A minimum of 0 lets the spell choose no target
    (115.6)."""

    objects: ObjectFilter | None = None
    players: PlayerFilter | None = None
    spells: SpellFilter | None = None
    minimum: int = 1
    maximum: int = 1

    def __post_init__(self) -> None:
        if self.objects is None and self.players is None and self.spells is None:
            raise ValueError("a target needs at least one kind of thing it may choose")
        if not 0 <= self.minimum <= self.maximum or self.maximum < 1:
            raise ValueError(
                f"a target needs 0 <= minimum <= maximum and maximum >= 1, "
                f"got {self.minimum}..{self.maximum}"
            )

    @property
    def text(self) -> str:
        """The instance as written: ``"target creature"``, ``"any target"``, ``"two target
        artifacts"``."""
        if self == ANY_TARGET:
            return "any target"
        nouns = [kind.text for kind in (self.objects, self.players, self.spells) if kind]
        noun = " or ".join(nouns)
        if self.minimum == self.maximum == 1:
            return f"target {noun}"
        if self.minimum == self.maximum:
            return f"{_count(self.maximum)} target {noun}s"
        if self.minimum == 0 and self.maximum == 1:
            return f"up to one target {noun}"
        return f"from {self.minimum} to {self.maximum} target {noun}s"


def _count(number: int) -> str:
    from resolve.cards.primitives.values import Fixed

    return Fixed(number).word


ANY_TARGET = TargetSpec(
    objects=ObjectFilter((CardType.CREATURE, CardType.PLANESWALKER, CardType.BATTLE)),
    players=PlayerFilter(),
)
"""115.4: "any target": a creature, planeswalker or battle, or a player."""


def target(*card_types: CardType, you_control: bool = False) -> TargetSpec:
    """ "target [card type]" (one permanent with one of the types), "... you control"."""
    return TargetSpec(objects=ObjectFilter(card_types, You() if you_control else None))
