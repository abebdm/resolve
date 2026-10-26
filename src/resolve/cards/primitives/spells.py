"""Spell abilities (113.3a): what an instant or sorcery does as it resolves (608.2c).

A ``SpellAbility`` is a definition's ``CardDefinition.spell``: its ``Mode`` (or, for a modal
spell, modes and a ``ModeChoice``, 700.2), each with its instances of the word "target"
(``TargetSpec``, 601.2c) and its effects (``resolve.cards.primitives.effects``) in the order
written. This module imports nothing from the engine, so ``CardDefinition`` can name it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from resolve.cards.primitives.base import Ability, Effect
from resolve.cards.primitives.refs import Phrasing, sentence
from resolve.cards.primitives.targets import TargetSpec
from resolve.cards.primitives.values import Fixed
from resolve.values import Immutable


def _number_word(number: int) -> str:
    return Fixed(number).word


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

    def __post_init__(self) -> None:
        if not 0 <= self.minimum <= self.maximum:
            raise ValueError(f"can't choose from {self.minimum} to {self.maximum} modes")

    def combinations(self, modes: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
        """Every choice of modes among ``modes`` (the indices of the legal ones, 700.2a, in
        printed order), each choice once: as many modes as allowed, smallest first, each
        choice listing its modes in printed order. A mode appears at most once (700.2d), or any
        number of times if ``repeatable``. A mode chosen more than once is that mode that many
        times in sequence (700.2d), so the order among its repetitions isn't a separate choice:
        their targets are chosen in order (601.2c)."""
        pick = (
            itertools.combinations_with_replacement if self.repeatable else itertools.combinations
        )
        return tuple(
            chosen
            for count in range(self.minimum, self.maximum + 1)
            for chosen in pick(modes, count)
            if chosen
        )

    def text(self, modes: int) -> str:
        """The instruction to choose, for a spell with ``modes`` modes: ``"Choose one —"``,
        ``"Choose three. You may choose the same mode more than once."``."""
        word = _number_word
        if self.minimum == self.maximum:
            how = word(self.minimum)
        elif self.minimum == 0:
            how = "any number" if self.maximum >= modes else f"up to {word(self.maximum)}"
        elif self.minimum == 1 and self.maximum >= modes:
            how = "one or both" if modes == 2 else "one or more"
        else:
            how = f"from {word(self.minimum)} to {word(self.maximum)}"
        if self.repeatable:
            return f"Choose {how}. You may choose the same mode more than once."
        return f"Choose {how} \u2014"


@dataclass(frozen=True)
class SpellAbility(Ability):
    """The spell ability of an instant or sorcery (113.3a): what it does as it resolves (608.2c).

    A nonmodal spell has one mode and ``choose`` is ``None``; a modal one (700.2) lists its modes
    and how many to choose, which its controller chooses as it is cast (601.2b). Its targets are
    chosen as it is cast (601.2c) and checked
    again as it resolves (608.2b).
    """

    modes: tuple[Mode, ...]
    choose: ModeChoice | None = None

    def __post_init__(self) -> None:
        if not self.modes:
            raise ValueError("a spell ability needs at least one mode")
        if self.choose is None and len(self.modes) != 1:
            raise ValueError("a nonmodal spell ability has exactly one mode")
        choose = self.choose
        if choose is not None and not choose.repeatable and choose.minimum > len(self.modes):
            raise ValueError("a spell can't choose more modes than it has without repeats")

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
        """The spell's text, such as ``"Draw a card."``; a modal spell's is the instruction to
        choose, then each mode on its own line after a bullet (700.2)."""
        if self.choose is None:
            return self.modes[0].text
        lines = [self.choose.text(len(self.modes))]
        lines += [f"\u2022 {mode.text}" for mode in self.modes]
        return "\n".join(lines)
