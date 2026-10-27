"""References: the objects and players a definition's text points at (design.md §17.9, §17.10).

A definition never names its own card (201.5) and never stores IDs: it refers to things with
these values, which ``resolve.effects.evaluation`` resolves as an effect applies (608.2h).

- ``ThisObject``: the object the text is on (201.5: a card's name in its own text means itself).
- ``TargetRef(index)``: what was chosen for the ``index``-th instance of the word "target"
  (601.2c); on resolution only the targets still legal (608.2b).
- ``You``: the controller of the spell or ability (109.5).
- ``ControllerOf(ref)``: the controller of an object (108.4), as it last existed if it has left
  its zone (608.2h).
- Groups, chosen as the effect applies (115.10, 608.2h): ``EachCreature(except_,
  controlled_by)`` (every creature on the battlefield, "each other creature" with an exception,
  "creatures your opponents control" with a controller) and ``EachOpponent`` (102.2, those
  still in the game: 800.4a).

``Phrasing`` writes the text of a spell ability from these, the first mention of a target in
full ("target creature you control") and later ones as "it".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from resolve.values import Immutable

if TYPE_CHECKING:
    from resolve.cards.primitives.targets import TargetSpec


@dataclass(frozen=True)
class ThisObject(Immutable):
    """The object whose text this is (201.5): a spell refers to itself this way."""


@dataclass(frozen=True)
class TargetRef(Immutable):
    """The objects and players chosen for instance number ``index`` (from 0, in the order of the
    text) of the word "target" (115.1, 601.2c). On resolution it is only those still legal: an
    illegal target isn't affected, and information about it can't be determined (608.2b)."""

    index: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("TargetRef needs an index of at least 0")


@dataclass(frozen=True)
class You(Immutable):
    """ "You": the controller of the spell or ability whose text this is (109.5)."""


@dataclass(frozen=True)
class ControllerOf(Immutable):
    """The controller of an object (108.4); if it has left the battlefield or the stack, its
    controller as it last existed there (608.2h)."""

    object: ObjectRef


@dataclass(frozen=True)
class EachOpponent(Immutable):
    """ "Each opponent": every opponent (102.2) of the controller still in the game when the
    effect applies (800.4a, 608.2h)."""


@dataclass(frozen=True)
class EachCreature(Immutable):
    """ "Each creature": every creature on the battlefield when the effect applies (608.2h),
    but ``except_`` ("each other creature", 115.10: not targets), and only those controlled by
    ``controlled_by`` if given ("creatures you control": ``You``; "creatures your opponents
    control": ``EachOpponent``, 108.4)."""

    except_: ObjectRef | None = None
    controlled_by: You | EachOpponent | None = None


ObjectRef = ThisObject | TargetRef
"""A reference to objects."""

PlayerRef = You | ControllerOf | TargetRef
"""A reference to players."""


@dataclass
class Phrasing:
    """Writes a mode's text: ``specs`` are its instances of "target" (``TargetSpec``), ``said``
    the targets already mentioned, which later mentions call "it". Used only while writing text,
    never stored."""

    specs: tuple[TargetSpec, ...]
    said: list[int] = field(default_factory=list[int])

    def object(self, ref: ObjectRef) -> str:
        """``ref`` as the subject or object of a sentence: "target creature", "it"."""
        match ref:
            case ThisObject():
                return "this spell"
            case TargetRef(index=index):
                if index in self.said:
                    return "it"
                self.said.append(index)
                return self.specs[index].text

    def possessive(self, ref: ObjectRef) -> str:
        """``ref`` owning something: "its", "target creature's"."""
        text = self.object(ref)
        return "its" if text == "it" else f"{text}'s"

    def player(self, ref: PlayerRef) -> str:
        """``ref`` as a player: "you", "its controller", "target player"."""
        match ref:
            case You():
                return "you"
            case ControllerOf(object=obj):
                return f"{self.possessive(obj)} controller"
            case TargetRef():
                return self.object(ref)


def sentence(text: str) -> str:
    """``text`` as a sentence: capitalized, ending with a period."""
    return text[0].upper() + text[1:] + "."
