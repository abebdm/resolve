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
| ``ChooseAssign-  | ``Assignment(picks)`` | per item, strictly increasing indices of its own    |
| ment``           |                       | choices, at most its maximum                        |
| ``DistributeEach``| ``AmountsEach(...)`` | per part, ``Amounts`` valid for that ``Distribute`` |

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

from resolve.data.types import Color
from resolve.errors import InvalidAnswer
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.spell import CastPermission, CastVariant
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
    """Cast the card ``object`` as a spell (117.1a, 601.2): as ``variant`` (601.3e: chosen before
    the card moves), under ``permission`` (601.3)."""

    object: ObjectId
    variant: CastVariant
    permission: CastPermission


@dataclass(frozen=True)
class ActivateAbilityOption(Immutable):
    """Activate ability number ``ability`` (from 0, in the order of the object's computed
    abilities) of ``object`` (117.1b, 602; mana abilities 605.3a)."""

    object: ObjectId
    ability: int


@dataclass(frozen=True)
class ManaOption(Immutable):
    """One class of identical units of mana in a pool: every unit equal to ``mana`` (106.4,
    601.2h). The option of a ``ChooseCounts`` payment."""

    mana: Mana


@dataclass(frozen=True)
class ManaActivationOption(Immutable):
    """A mana ability activated during an action: the ``number``-th activation (from 0), of
    ability ``ability`` of ``object`` (733.1: which to reverse)."""

    number: int
    object: ObjectId
    ability: int


@dataclass(frozen=True)
class ModesOption(Immutable):
    """A choice of modes for a modal spell (700.2, 601.2b): ``modes`` by index from 0, in
    printed order, a mode chosen more than once listed that many times (700.2d)."""

    modes: tuple[int, ...]


@dataclass(frozen=True)
class ColorOption(Immutable):
    """A color (105.1), such as the color of the mana an ability adds (106.1a)."""

    color: Color


Option = (
    PlayerOption
    | ObjectOption
    | NamedOption
    | PassOption
    | PlayLandOption
    | CastSpellOption
    | ActivateAbilityOption
    | ManaOption
    | ManaActivationOption
    | ModesOption
    | ColorOption
)

# --- Constraints of declarations --------------------------------------------------------------


@dataclass(frozen=True)
class NoneOrAtLeast(Immutable):
    """A constraint of a ``ChooseAssignment`` (design.md §17.18): ``choice`` is picked by no item
    or by at least ``minimum`` items. Menace (702.111b): an attacker blocked by none or by two or
    more creatures. Choices are compared by value, so the same attacker offered to several
    blockers is one choice."""

    choice: Option
    minimum: int

    def __post_init__(self) -> None:
        if self.minimum < 2:
            raise ValueError(f"NoneOrAtLeast needs a minimum of at least 2, got {self.minimum}")


Constraint = NoneOrAtLeast
"""The closed vocabulary of declaration-wide constraints (design.md §17.18); ``NotAlone`` and
``AtMost`` join it in M3.5."""


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


@dataclass(frozen=True)
class Assignment(Immutable):
    """For each item of a ``ChooseAssignment``, in item order, the indices of the choices it
    picks, in increasing order (none: an empty tuple)."""

    picks: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class AmountsEach(Immutable):
    """For each part of a ``DistributeEach``, in part order, its ``Amounts``."""

    amounts: tuple[Amounts, ...]


AnswerValue = Pick | PickMany | Order | Number | Amounts | Assignment | AmountsEach


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

    The space for paying mana (601.2h, design.md §6 "Paying costs"): each option is a class of
    identical units in the pool, and the answer says how many of each class to spend. Per-unit
    options would give several answers for one outcome, which the canonical-answer rule (§6)
    forbids; counts give exactly one.
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


@dataclass(frozen=True)
class ChooseAssignment(AnswerSpace):
    """Give each item up to its maximum of its own choices (design.md §17.8, §17.18).

    The space of attack and block declarations (508.1, 509.1): the items are the creatures that
    may attack (or block), ``choices[i]`` what item ``i`` may pick (what it may attack, or the
    attackers it may block), and ``maxima[i]`` how many it may pick (1 to attack, 508.1b;
    ``defaults.blocks_allowed`` to block, 509.1a). Any item may pick nothing ("if any", 508.1a,
    509.1a). The answer, ``Assignment``, gives each item strictly increasing choice indices, so
    one declaration has exactly one answer (§6).

    ``constraints`` are the declaration-wide restrictions (509.1b; §17.18's closed vocabulary,
    ``Constraint``): an answer must satisfy every one, checked by the solver
    (``resolve.decisions.assignment``) without the state. Requirements and the picks that need a
    cost (508.1c-d, 509.1c) join it in M3.5.
    """

    items: tuple[Option, ...]
    choices: tuple[tuple[Option, ...], ...]
    maxima: tuple[int, ...]
    constraints: tuple[Constraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("ChooseAssignment needs at least one item")
        if len(self.choices) != len(self.items):
            raise ValueError(
                f"ChooseAssignment needs one tuple of choices per item: {len(self.items)} items, "
                f"{len(self.choices)} choices"
            )
        if len(self.maxima) != len(self.items):
            raise ValueError(
                f"ChooseAssignment needs one maximum per item: {len(self.items)} items, "
                f"{len(self.maxima)} maxima"
            )
        for choices, maximum in zip(self.choices, self.maxima, strict=True):
            if not 0 <= maximum <= len(choices):
                raise ValueError(
                    f"ChooseAssignment needs each maximum from 0 to its item's number of "
                    f"choices, got {maximum} for {len(choices)}"
                )

    def validate(self, answer: AnswerValue) -> None:
        picks = _expect(answer, Assignment).picks
        # An agent's answer: its types are checked, not trusted.
        if not isinstance(picks, tuple):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise InvalidAnswer("the picks must be a tuple, one per item")
        items: tuple[object, ...] = picks  # pyright: ignore[reportUnknownVariableType]
        if len(items) != len(self.items):
            raise InvalidAnswer(f"give exactly one tuple of picks for each of {len(self.items)}")
        for number, (item, choices, maximum) in enumerate(
            zip(items, self.choices, self.maxima, strict=True)
        ):
            indices = _int_tuple(item, f"item {number}'s picks")
            if any(index < 0 or index >= len(choices) for index in indices):
                raise InvalidAnswer(
                    f"item {number} has {len(choices)} choices; its picks must be indices of them"
                )
            if any(a >= b for a, b in pairwise(indices)):
                raise InvalidAnswer(
                    f"item {number}'s picks must be strictly increasing (no repeats)"
                )
            if len(indices) > maximum:
                raise InvalidAnswer(f"item {number} may pick at most {maximum}")

    def chosen(self, answer: Assignment) -> tuple[tuple[Option, ...], ...]:
        """The choices an (already validated) answer gives each item, in choice order."""
        return tuple(
            tuple(choices[index] for index in picks)
            for choices, picks in zip(self.choices, answer.picks, strict=True)
        )


@dataclass(frozen=True)
class DistributeEach(AnswerSpace):
    """Divide each part's total among its recipients, the parts answered together (design.md
    §17.8, §17.18).

    The space of combat damage assignment (510.1): one ``Distribute`` per creature that has a
    choice, ``sources[i]`` naming the creature whose damage ``parts[i]`` divides. It is one
    space because 510.1e checks the total assignment, not each creature's; the constraint that
    needs it (trample's lethal damage first, 702.19b) joins it in M3.6. The answer,
    ``AmountsEach``, gives one ``Amounts`` per part, each valid for its part.
    """

    sources: tuple[Option, ...]
    parts: tuple[Distribute, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("DistributeEach needs at least one part")
        if len(self.sources) != len(self.parts):
            raise ValueError(
                f"DistributeEach needs one source per part: {len(self.parts)} parts, "
                f"{len(self.sources)} sources"
            )

    def validate(self, answer: AnswerValue) -> None:
        amounts = _expect(answer, AmountsEach).amounts
        # An agent's answer: its types are checked, not trusted.
        if not isinstance(amounts, tuple):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise InvalidAnswer("the amounts must be a tuple, one Amounts per part")
        each: tuple[object, ...] = amounts  # pyright: ignore[reportUnknownVariableType]
        if len(each) != len(self.parts):
            raise InvalidAnswer(f"give exactly one Amounts for each of {len(self.parts)} parts")
        for number, (part_answer, part) in enumerate(zip(each, self.parts, strict=True)):
            if not isinstance(part_answer, Amounts):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise InvalidAnswer(f"part {number}'s answer must be an Amounts")
            try:
                part.validate(part_answer)
            except InvalidAnswer as error:
                raise InvalidAnswer(f"part {number}: {error}") from None
