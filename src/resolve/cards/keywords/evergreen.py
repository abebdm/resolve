"""Evergreen keyword abilities of M2 (702.8, 702.11, 702.12, 702.16, 702.18).

Each is an ``Ability`` value a definition lists (or, from M5, an effect grants), read only
through an object's computed characteristics (``has_keyword``, ``keywords``) or, for a player,
``defaults.player_abilities``. What each one does lives where the rule it changes is decided:

- ``Flash`` (702.8a): instant timing, in ``defaults.may_cast_now``.
- ``Hexproof``, ``Shroud`` and ``Protection`` (702.11b-d, 702.18a, 702.16b, 702.16j): the
  prohibitions of ``legality.allowed(TargetAction)``, used by ``targeting.target_problem``.
  Protection's other parts arrive with their systems: blocking (702.16f, M3), Auras and Equipment
  (702.16c-d, M4) and damage prevention (702.16e, M6; until then its damage is a gap in
  ``DamageDealt.apply``).
- ``Indestructible`` (702.12b): the prohibition of ``legality.allowed(DestroyAction)``, used by
  ``Destroy`` and by 704.5g.

"From A and from B" and "from each [characteristic]" are separate abilities (702.16g-h,
702.11f-g: ``protection_from_each_color``). Multiple instances are redundant (702.8b, 702.11h,
702.12c, 702.16m, 702.18b): each is checked on its own, and none counts twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resolve.cards.keywords.qualities import Quality, each_color
from resolve.cards.primitives.base import Ability

if TYPE_CHECKING:
    from resolve.effects.characteristics import Characteristics


@dataclass(frozen=True)
class Flash(Ability):
    """702.8a: "You may play this card any time you could cast an instant." It functions in any
    zone from which the card could be played; it gives no permission to cast from a zone."""

    @property
    def text(self) -> str:
        return "Flash"


@dataclass(frozen=True)
class Hexproof(Ability):
    """702.11b-c: this permanent (or player) can't be the target of spells or abilities its
    controller's (or the player's) opponents control. With a ``quality``, "hexproof from
    [quality]" (702.11d): only [quality] spells those opponents control and abilities they
    control from [quality] sources; it is a hexproof ability (702.11d-e)."""

    quality: Quality | None = None

    @property
    def text(self) -> str:
        return "Hexproof" if self.quality is None else f"Hexproof from {self.quality.text}"


@dataclass(frozen=True)
class Shroud(Ability):
    """702.18a: this permanent or player can't be the target of spells or abilities."""

    @property
    def text(self) -> str:
        return "Shroud"


@dataclass(frozen=True)
class Indestructible(Ability):
    """702.12b: this permanent can't be destroyed; lethal damage doesn't destroy it (704.5g)."""

    @property
    def text(self) -> str:
        return "Indestructible"


@dataclass(frozen=True)
class Protection(Ability):
    """702.16a: "protection from [quality]". The permanent or player can't be targeted by spells
    with the quality or by abilities from a source with it, whoever controls them (702.16b);
    from everything, by no spell or ability at all (702.16j)."""

    quality: Quality

    @property
    def text(self) -> str:
        return f"Protection from {self.quality.text}"


def protection_from_each_color() -> tuple[Protection, ...]:
    """ "Protection from each color": five protection abilities, one per color (702.16h)."""
    return tuple(Protection(quality) for quality in each_color())


def keywords[A: Ability](characteristics: Characteristics, kind: type[A]) -> tuple[A, ...]:
    """The object's abilities of the keyword ``kind``, in order (several instances may be
    listed: 702.16g-h)."""
    return tuple(a for a in characteristics.abilities if isinstance(a, kind))


def has_keyword(characteristics: Characteristics, kind: type[Ability]) -> bool:
    """Whether the object has at least one ability of the keyword ``kind`` (113.1, 702)."""
    return any(isinstance(a, kind) for a in characteristics.abilities)
