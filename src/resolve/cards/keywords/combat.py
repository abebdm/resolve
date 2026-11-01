"""The evasion keywords and reach (702.9, 702.13, 702.14, 702.17, 702.36, 702.111).

Each is an ``Ability`` value a definition lists (or, from M5, an effect grants), read only through
the attacking creature's (or, for reach and flying, the blocker's) computed characteristics. What
each one does lives where blocks are judged (509.1b: evasion abilities are restrictions, and
cumulative):

- ``Flying`` and ``Reach`` (702.9b, 702.17b): prohibitions of ``legality.allowed(BlockAction)``;
- ``Intimidate`` (702.13b), ``Fear`` (702.36b) and ``Landwalk`` (702.14c): the same;
- ``Menace`` (702.111b): a constraint on the whole declaration, ``NoneOrAtLeast`` (compiled by
  ``resolve.rules.combat.block_declaration``), because it concerns how many creatures block, not
  one blocker.

Multiple instances are redundant (702.9c, 702.13c, 702.14e, 702.17c, 702.36c, 702.111c).
Different landwalk abilities don't cancel one another (702.14d).
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.keywords.qualities import LandTypeQuality, Quality
from resolve.cards.primitives.base import Ability


@dataclass(frozen=True)
class Flying(Ability):
    """702.9b: this creature can't be blocked except by creatures with flying and/or reach. It
    can block a creature with or without flying."""

    @property
    def text(self) -> str:
        return "Flying"


@dataclass(frozen=True)
class Reach(Ability):
    """702.17b: this creature can block creatures with flying (the exception of 702.9b)."""

    @property
    def text(self) -> str:
        return "Reach"


@dataclass(frozen=True)
class Menace(Ability):
    """702.111b: this creature can't be blocked except by two or more creatures."""

    @property
    def text(self) -> str:
        return "Menace"


@dataclass(frozen=True)
class Intimidate(Ability):
    """702.13b: this creature can't be blocked except by artifact creatures and/or creatures that
    share a color with it."""

    @property
    def text(self) -> str:
        return "Intimidate"


@dataclass(frozen=True)
class Fear(Ability):
    """702.36b: this creature can't be blocked except by artifact creatures and/or black
    creatures."""

    @property
    def text(self) -> str:
        return "Fear"


@dataclass(frozen=True)
class Landwalk(Ability):
    """702.14a, c: "[quality]walk": this creature can't be blocked as long as the defending player
    (the player it attacks, 802.2a) controls at least one land with ``quality``.

    ``quality`` judges the land's characteristics: a land type (``LandTypeQuality``, "swampwalk",
    rewritable by text-changing effects, 612.2), or one of 702.14a's combinations of types and
    supertypes ("artifact landwalk") as another quality. "Nonbasic landwalk" (a land *without*
    a supertype) needs a negated quality, which doesn't exist yet.
    """

    quality: Quality

    @property
    def text(self) -> str:
        if isinstance(self.quality, LandTypeQuality):
            return f"{self.quality.word.name.capitalize()}walk"
        return f"{self.quality.adjective.capitalize()} landwalk"
