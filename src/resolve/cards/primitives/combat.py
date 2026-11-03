"""Static abilities of creatures that change how they attack or block (506-509; design.md §17.18),
read through the creature's computed characteristics, so granted ones (M5) need no change.

So far:

- ``BlocksAnyNumber``, "This creature can block any number of creatures." (Palace Guard), read by
  ``defaults.blocks_allowed`` (509.1a);
- ``CantBeBlocked``, "This creature can't be blocked." (Phantom Warrior), a prohibition of
  ``legality.allowed(BlockAction)`` read from the attacker (509.1b);
- ``PowerBlockRestriction``, "Creatures with power less than this creature's power can't block
  creatures you control." (Champion of Lambholt), a prohibition of the same, collected from the
  permanents on the battlefield (509.1b), as M2.9 collects cost modifiers.

- ``CantBeBlockedBy(quality)``, "This creature can't be blocked by Walls." (Juggernaut), a
  prohibition of the same, read from the attacker (509.1b);
- ``CantAttackOrBlockUnless(condition)``, "This creature can't attack or block unless you control
  seven or more lands." (Topiary Stomper), prohibitions of ``AttackAction`` and ``BlockAction``
  (508.1c, 509.1b);
- ``CantAttackOrBlockAlone``, "This creature can't attack or block alone." (Mogg Flunkies), a
  ``NotAlone`` constraint of the declaration (506.5, 508.1c, 509.1b);
- ``AtMostCreatures(count, blocking)``, "No more than one creature can attack (block) each
  combat." (Silent Arbiter), an ``AtMost`` constraint, collected from the battlefield;
- ``AttacksEachCombat(scope)``, "This creature attacks each combat if able." (Juggernaut) and
  "Creatures you control attack each combat if able." (``CreaturesYouControl``), requirements
  (508.1d);
- ``BlocksEachCombat``, "This creature blocks each combat if able." (509.1c's example);
- ``MustBeBlockedByAll``, "All creatures able to block this creature do so." (Prized Unicorn),
  a requirement on each creature able to block it (509.1c);
- ``AttackTax(cost)``, "Creatures can't attack you unless their controller pays {2} for each
  creature they control that's attacking you." (Ghostly Prison), and ``BlockTax(cost)``, its
  blocking counterpart: costs to attack and block (508.1h, 509.1d), collected from the
  battlefield.

``resolve.rules.combat`` compiles the declaration-wide ones into the declaration's space
(design.md §17.18).
"""

from __future__ import annotations

from dataclasses import dataclass

from resolve.cards.keywords.qualities import Quality
from resolve.cards.primitives.base import Ability
from resolve.cards.primitives.conditions import NUMBER_WORDS, ControlsAtLeast
from resolve.cards.primitives.refs import ThisObject
from resolve.data.mana_cost import ManaCost
from resolve.values import Immutable

_THIS_OBJECT = ThisObject()


@dataclass(frozen=True)
class CreaturesYouControl(Immutable):
    """The scope "creatures you control": each creature the ability's controller controls, the
    permanent itself included when it is one (109.5, 108.4)."""


def _number(count: int) -> str:
    return NUMBER_WORDS[count] if count < len(NUMBER_WORDS) else str(count)


@dataclass(frozen=True)
class BlocksAnyNumber(Ability):
    """ "This creature can block any number of creatures." (509.1a): it may block any number of
    the creatures attacking its controller, instead of one. ``defaults.blocks_allowed`` reads it
    (``None``: no limit); 509.1a's other conditions (untapped, attacking that player) still
    apply. Several instances are redundant."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This creature can block any number of creatures."


@dataclass(frozen=True)
class CantBeBlocked(Ability):
    """ "This creature can't be blocked.": a restriction on every creature that would block it
    (509.1b), checked as blockers are declared; it doesn't remove a block already declared."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This creature can't be blocked."


@dataclass(frozen=True)
class PowerBlockRestriction(Ability):
    """ "Creatures with power less than this creature's power can't block creatures you
    control." (Champion of Lambholt): while its permanent is on the battlefield, a creature whose
    power is less than the permanent's can't block a creature the permanent's controller controls,
    whether or not the permanent is attacking (its ruling). A restriction (509.1b): the powers are
    compared only as blockers are declared, so later changes don't undo a block (its ruling)."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return (
            "Creatures with power less than this creature's power can't block creatures you "
            "control."
        )


@dataclass(frozen=True)
class CantBeBlockedBy(Ability):
    """ "This creature can't be blocked by [quality]." (Juggernaut: Walls): a restriction on each
    creature with the quality that would block it (509.1b), judged by its computed
    characteristics as blockers are declared."""

    quality: Quality
    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return f"This creature can't be blocked by {self.quality.text}."


@dataclass(frozen=True)
class CantAttackOrBlockUnless(Ability):
    """ "This creature can't attack or block unless [condition]." (Topiary Stomper): a
    restriction (508.1c, 509.1b), the condition judged for the creature's controller as the
    declaration is made."""

    condition: ControlsAtLeast
    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return f"This creature can't attack or block unless {self.condition.clause}."


@dataclass(frozen=True)
class CantAttackOrBlockAlone(Ability):
    """ "This creature can't attack or block alone." (Mogg Flunkies): a restriction on the whole
    declaration (506.5, 508.1c, 509.1b): it attacks (blocks) only if another creature is declared
    with it, whatever that one attacks (blocks) (its rulings). Once declared, it stays in combat
    alone (its ruling)."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This creature can't attack or block alone."


@dataclass(frozen=True)
class AtMostCreatures(Ability):
    """ "No more than [count] creature(s) can attack each combat." or, with ``blocking``, "... can
    block each combat." (Silent Arbiter, one ability each): a restriction on the whole
    declaration (508.1c, 509.1b), while its permanent is on the battlefield, whoever controls it.
    The M3 plan's ``AtMostCreaturesAttackAndBlock``, written as two abilities as the Oracle text
    has them."""

    count: int
    blocking: bool

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("AtMostCreatures needs a count of at least 1")

    @property
    def text(self) -> str:
        noun = "creature" if self.count == 1 else "creatures"
        verb = "block" if self.blocking else "attack"
        return f"No more than {_number(self.count)} {noun} can {verb} each combat."


@dataclass(frozen=True)
class AttacksEachCombat(Ability):
    """ "[This creature attacks / Creatures you control attack] each combat if able." (Juggernaut;
    Test Warmonger): a requirement on each creature in its scope (508.1d), obeyed by attacking
    anything. Each instance is a requirement of its own. It doesn't make a creature able to
    attack (tapped, summoning sick) or force paying a cost (Juggernaut's ruling)."""

    scope: ThisObject | CreaturesYouControl = _THIS_OBJECT

    @property
    def text(self) -> str:
        if isinstance(self.scope, CreaturesYouControl):
            return "Creatures you control attack each combat if able."
        return "This creature attacks each combat if able."


@dataclass(frozen=True)
class BlocksEachCombat(Ability):
    """ "This creature blocks each combat if able." (509.1c's example): a requirement (509.1c),
    obeyed by blocking any attacker."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "This creature blocks each combat if able."


@dataclass(frozen=True)
class MustBeBlockedByAll(Ability):
    """ "All creatures able to block this creature do so." (Prized Unicorn): while it attacks, a
    requirement on each creature able to block it (509.1c), obeyed by blocking it. A creature
    that can't block it, or only by paying a cost, needn't (its ruling); with two of them, each
    creature blocks one, not necessarily the same (its ruling)."""

    scope: ThisObject = _THIS_OBJECT

    @property
    def text(self) -> str:
        return "All creatures able to block this creature do so."


@dataclass(frozen=True)
class AttackTax(Ability):
    """ "Creatures can't attack you unless their controller pays [cost] for each creature they
    control that's attacking you." (Ghostly Prison): attacking its controller with a creature is
    a costly pick (508.1d, 508.1h): the cost is added to the total cost to attack once for each
    creature attacking that player, for each instance. A creature attacking another player
    (or, from M4, a planeswalker, its ruling) costs nothing."""

    cost: ManaCost

    @property
    def text(self) -> str:
        return (
            f"Creatures can't attack you unless their controller pays {self.cost.text} for each "
            "creature they control that's attacking you."
        )


@dataclass(frozen=True)
class BlockTax(Ability):
    """ "Creatures can't block unless their controller pays [cost] for each creature they control
    that's blocking." (Test Tollkeeper): blocking is a costly pick (509.1c-d): the cost is added
    to the total cost to block once for each blocking creature (whatever it blocks), for each
    instance, whoever controls the permanent."""

    cost: ManaCost

    @property
    def text(self) -> str:
        return (
            f"Creatures can't block unless their controller pays {self.cost.text} for each "
            "creature they control that's blocking."
        )
