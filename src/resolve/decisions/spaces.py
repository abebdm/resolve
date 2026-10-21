"""Answer spaces and answer values (design.md §6).

An answer space describes every answer a decision accepts:

| Space            | Answer value          | Valid when                                         |
|------------------|-----------------------|----------------------------------------------------|
| ``ChooseOne``    | ``Pick(index)``       | ``0 <= index < len(options)``                      |
| ``ChooseSubset`` | ``PickMany(indices)`` | strictly increasing indices, count within bounds   |
| ``ChooseOrder``  | ``Order(permutation)``| a permutation of ``0 .. len(options) - 1``         |
| ``ChooseNumber`` | ``Number(value)``     | ``minimum <= value <= maximum``                    |
| ``Distribute``   | ``Amounts(amounts)``  | one amount per recipient, each at least             |
|                  |                       | ``minimum_each``, adding up to ``total``           |
| ``ChooseCounts`` | ``Amounts(amounts)``  | one amount per option, each from 0 to its maximum,  |
|                  |                       | adding up to ``total``                              |

``ChooseOne`` lists every option (an *enumerated* space, which the AI will search). The others are
*constrained* spaces, described by bounds rather than listed.

Every outcome has exactly one valid answer (for example, a subset is given as sorted indices), so
two answers that mean the same thing are always equal.

``validate`` checks only the shape and bounds. Rules that a space can't express (targets that must
be distinct objects with some property, say) are checked by the asking task's ``check_answer``.
Invalid answers raise ``InvalidAnswer``; a space that can't be answered at all is an engine bug
and raises ``ValueError`` when it is built.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import pairwise

from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId, PlayerId
from resolve.values import Immutable

# --- Options -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerOption(Immutable):
    """An option that is a player."""

    player: PlayerId


@dataclass(frozen=True)
class ObjectOption(Immutable):
    """An option that is a game object."""

    object: ObjectId


@dataclass(frozen=True)
class NamedOption(Immutable):
    """An option that is neither a player nor an object, named by a fixed word ("keep")."""

    name: str


@dataclass(frozen=True)
class PassOption(Immutable):
    """Pass priority (117.3d)."""


@dataclass(frozen=True)
class PlayLandOption(Immutable):
    """Play the land card ``object`` (305.1, a special action: 116.2a)."""

    object: ObjectId


@dataclass(frozen=True)
class CastSpellOption(Immutable):
    """Cast the card ``object`` as a spell (117.1a, 601.2)."""

    object: ObjectId


@dataclass(frozen=True)
class ActivateAbilityOption(Immutable):
    """Activate ability number ``ability`` (from 0, in the order of the object's computed
    abilities) of ``object`` (117.1b, 602; mana abilities 605.3a)."""

    object: ObjectId
    ability: int


Option = (
    PlayerOption
    | ObjectOption
    | NamedOption
    | PassOption
    | PlayLandOption
    | CastSpellOption
    | ActivateAbilityOption
)

# --- Answer values -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Pick(Immutable):
    """The index of the chosen option."""

    index: int


@dataclass(frozen=True)
class PickMany(Immutable):
    """The indices of the chosen options, in increasing order."""

    indices: tuple[int, ...]


@dataclass(frozen=True)
class Order(Immutable):
    """Option indices in the chosen order (first = first in the order)."""

    permutation: tuple[int, ...]


@dataclass(frozen=True)
class Number(Immutable):
    """A chosen number."""

    value: int


@dataclass(frozen=True)
class Amounts(Immutable):
    """The amount given to each recipient, in recipient order."""

    amounts: tuple[int, ...]


AnswerValue = Pick | PickMany | Order | Number | Amounts


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int_tuple(value: object, what: str) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise InvalidAnswer(f"{what} must be a tuple of integers")
    items: tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
    if not all(_is_int(item) for item in items):
        raise InvalidAnswer(f"{what} must be a tuple of integers")
    return tuple(int(item) for item in items)  # pyright: ignore[reportArgumentType]


def _expect[T](answer: object, expected: type[T]) -> T:
    if not isinstance(answer, expected):
        raise InvalidAnswer(f"expected a {expected.__name__} answer, got {answer!r}")
    return answer


# --- Spaces ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerSpace(Immutable, ABC):
    """The set of answers a decision accepts."""

    @abstractmethod
    def validate(self, answer: AnswerValue) -> None:
        """Raise ``InvalidAnswer`` unless ``answer`` is in this space."""


@dataclass(frozen=True)
class ChooseOne(AnswerSpace):
    """Choose exactly one of a listed set of options."""

    options: tuple[Option, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("ChooseOne needs at least one option")

    def validate(self, answer: AnswerValue) -> None:
        pick = _expect(answer, Pick)
        if not _is_int(pick.index) or not 0 <= pick.index < len(self.options):
            raise InvalidAnswer(f"option index must be in 0..{len(self.options) - 1}")

    def chosen(self, answer: Pick) -> Option:
        """The option an (already validated) answer picks."""
        return self.options[answer.index]


@dataclass(frozen=True)
class ChooseSubset(AnswerSpace):
    """Choose between ``minimum`` and ``maximum`` of the listed options (no repeats)."""

    options: tuple[Option, ...]
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if not 0 <= self.minimum <= self.maximum <= len(self.options):
            raise ValueError(
                f"ChooseSubset needs 0 <= minimum <= maximum <= {len(self.options)}, "
                f"got {self.minimum}..{self.maximum}"
            )

    def validate(self, answer: AnswerValue) -> None:
        indices = _int_tuple(_expect(answer, PickMany).indices, "indices")
        if any(index < 0 or index >= len(self.options) for index in indices):
            raise InvalidAnswer(f"option indices must be in 0..{len(self.options) - 1}")
        if any(a >= b for a, b in pairwise(indices)):
            raise InvalidAnswer("option indices must be strictly increasing (no repeats)")
        if not self.minimum <= len(indices) <= self.maximum:
            raise InvalidAnswer(f"choose between {self.minimum} and {self.maximum} options")

    def chosen(self, answer: PickMany) -> tuple[Option, ...]:
        """The options an (already validated) answer picks, in option order."""
        return tuple(self.options[index] for index in answer.indices)


@dataclass(frozen=True)
class ChooseOrder(AnswerSpace):
    """Put all the listed options in an order."""

    options: tuple[Option, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("ChooseOrder needs at least one option")

    def validate(self, answer: AnswerValue) -> None:
        permutation = _int_tuple(_expect(answer, Order).permutation, "permutation")
        if sorted(permutation) != list(range(len(self.options))):
            raise InvalidAnswer(
                f"the order must list each option index 0..{len(self.options) - 1} exactly once"
            )

    def chosen(self, answer: Order) -> tuple[Option, ...]:
        """The options in the order an (already validated) answer gives."""
        return tuple(self.options[index] for index in answer.permutation)


@dataclass(frozen=True)
class ChooseNumber(AnswerSpace):
    """Choose an integer between ``minimum`` and ``maximum`` (``None``: no upper bound)."""

    minimum: int
    maximum: int | None = None

    def __post_init__(self) -> None:
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError(f"ChooseNumber has maximum {self.maximum} < minimum {self.minimum}")

    def validate(self, answer: AnswerValue) -> None:
        value = _expect(answer, Number).value
        if not _is_int(value):
            raise InvalidAnswer("the number must be an integer")
        if value < self.minimum or (self.maximum is not None and value > self.maximum):
            upper = "" if self.maximum is None else f" and at most {self.maximum}"
            raise InvalidAnswer(f"the number must be at least {self.minimum}{upper}")


@dataclass(frozen=True)
class Distribute(AnswerSpace):
    """Divide ``total`` among the recipients, at least ``minimum_each`` to each (601.2d)."""

    recipients: tuple[Option, ...]
    total: int
    minimum_each: int = 1

    def __post_init__(self) -> None:
        if not self.recipients:
            raise ValueError("Distribute needs at least one recipient")
        if self.minimum_each < 0 or self.minimum_each * len(self.recipients) > self.total:
            raise ValueError(
                f"can't give {len(self.recipients)} recipients at least {self.minimum_each} "
                f"each out of {self.total}"
            )

    def validate(self, answer: AnswerValue) -> None:
        amounts = _int_tuple(_expect(answer, Amounts).amounts, "amounts")
        if len(amounts) != len(self.recipients):
            raise InvalidAnswer(f"give exactly one amount for each of {len(self.recipients)}")
        if any(amount < self.minimum_each for amount in amounts):
            raise InvalidAnswer(f"each recipient must get at least {self.minimum_each}")
        if sum(amounts) != self.total:
            raise InvalidAnswer(f"the amounts must add up to {self.total}, not {sum(amounts)}")


@dataclass(frozen=True)
class ChooseCounts(AnswerSpace):
    """Choose how many of each listed option, from none up to its maximum, adding up to ``total``.

    The space for paying mana (601.2h, design.md §17.7): each option is a class of identical
    units in the pool, and the answer says how many of each class to spend. Per-unit options
    would give several answers for one outcome, which the canonical-answer rule (§6) forbids;
    counts give exactly one.
    """

    options: tuple[Option, ...]
    maxima: tuple[int, ...]
    total: int

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("ChooseCounts needs at least one option")
        if len(self.maxima) != len(self.options):
            raise ValueError(
                f"ChooseCounts needs one maximum per option: {len(self.options)} options, "
                f"{len(self.maxima)} maxima"
            )
        if any(maximum < 0 for maximum in self.maxima) or self.total < 0:
            raise ValueError("ChooseCounts can't have a negative maximum or total")
        if sum(self.maxima) < self.total:
            raise ValueError(
                f"ChooseCounts can't reach a total of {self.total} with maxima {self.maxima}"
            )

    def validate(self, answer: AnswerValue) -> None:
        amounts = _int_tuple(_expect(answer, Amounts).amounts, "amounts")
        if len(amounts) != len(self.options):
            raise InvalidAnswer(f"give exactly one amount for each of {len(self.options)}")
        for amount, maximum in zip(amounts, self.maxima, strict=True):
            if not 0 <= amount <= maximum:
                raise InvalidAnswer(f"each amount must be between 0 and its maximum {maximum}")
        if sum(amounts) != self.total:
            raise InvalidAnswer(f"the amounts must add up to {self.total}, not {sum(amounts)}")
