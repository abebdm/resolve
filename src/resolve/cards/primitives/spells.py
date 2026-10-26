"""Spell abilities (113.3a): what an instant or sorcery does as it resolves (608.2c).

A ``SpellAbility`` is a definition's ``CardDefinition.spell``: its ``Mode`` (or, for a modal
spell, modes and a ``ModeChoice``, 700.2, M2.7), each with its instances of the word "target"
(``TargetSpec``, 601.2c) and its effects (``resolve.cards.primitives.effects``) in the order
written. This module imports nothing from the engine, so ``CardDefinition`` can name it.
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.primitives.base import Ability, Effect
from resolve.cards.primitives.refs import Phrasing, sentence
from resolve.cards.primitives.targets import TargetSpec
from resolve.errors import NotImplementedRule
from resolve.values import Immutable


@dataclass(frozen=True)
class Mode(Immutable):
    """One mode of a spell ability (700.2), or the whole of a nonmodal one: its instances of the
    word "target" in the order written (``targets``, 115.1, 601.2c) and its effects in the order
    written (608.2c). ``cost`` leaves room for a mode with its own cost (spree, 702.172, M9)."""

    targets: tuple[TargetSpec, ...]
    effects: tuple[Effect, ...]
    cost: None = None

    def __post_init__(self) -> None:
        if not self.effects:
            raise ValueError("a mode needs at least one effect")

    @property
    def text(self) -> str:
        """The mode's text, written from its effects: ``"Exile target creature. Its controller
        gains life equal to its power."``."""
        phrasing = Phrasing(self.targets)
        return " ".join(sentence(effect.describe(phrasing)) for effect in self.effects)


@dataclass(frozen=True)
class ModeChoice(Immutable):
    """How many modes a modal spell chooses (700.2): from ``minimum`` to ``maximum``, the same
    mode more than once if ``repeatable`` (700.2d)."""

    minimum: int
    maximum: int
    repeatable: bool = False

    def combinations(self, modes: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
        """Every choice of modes among ``modes`` (the legal ones, 700.2a)."""
        raise NotImplementedRule("700.2: choosing the modes of a modal spell (M2.7)")


@dataclass(frozen=True)
class SpellAbility(Ability):
    """The spell ability of an instant or sorcery (113.3a): what it does as it resolves (608.2c).

    A nonmodal spell has one mode and ``choose`` is ``None``; a modal one (700.2) lists its modes
    and how many to choose (M2.7). Its targets are chosen as it is cast (601.2c) and checked
    again as it resolves (608.2b).
    """

    modes: tuple[Mode, ...]
    choose: ModeChoice | None = None

    def __post_init__(self) -> None:
        if not self.modes:
            raise ValueError("a spell ability needs at least one mode")
        if self.choose is None and len(self.modes) != 1:
            raise ValueError("a nonmodal spell ability has exactly one mode")

    def chosen(self, modes: tuple[int, ...]) -> tuple[Mode, ...]:
        """The modes that a spell with this ability and the record's ``modes`` follows, in order
        (608.2c, 700.2d): its one mode if it isn't modal."""
        if self.choose is None:
            return self.modes
        return tuple(self.modes[index] for index in modes)

    def instances(self, modes: tuple[int, ...]) -> tuple[TargetSpec, ...]:
        """The instances of the word "target" of the chosen ``modes``, in order (601.2c, 700.2c):
        each chosen mode's, in turn."""
        return tuple(spec for mode in self.chosen(modes) for spec in mode.targets)

    @property
    def text(self) -> str:
        """The spell's text, such as ``"Draw a card."``."""
        if self.choose is not None:
            raise NotImplementedRule("700.2: the text of a modal spell (M2.7)")
        return self.modes[0].text
