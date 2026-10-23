"""How a spell is cast, and the record a spell carries on the stack (601.2, design.md §17.3, §17.5).

Every way of casting that changes a spell's characteristics is chosen before the card moves to the
stack (601.3e): a **cast variant**. Every cast happens under a **cast permission**: a rule or an
effect that allows it (601.3), with the zone it allows casting from and its timing.

- ``CastVariant``: ``Normal`` (``NORMAL``), ``Half(i)`` of a split card (709.3), ``Fused``
  (702.102), ``Back`` (712.11a-b), ``Alternative(kind)`` for an adventure, an Omen or a
  prototype (715.3, 720.3, 718.3), or ``FaceDown(kind)`` (708.4).
- ``CastPermission``: the rule (or effect) that allows the cast, the zone the card is cast from,
  and its timing. The rules' own are ``FROM_HAND`` (601.3, 117.1a) and ``COMMANDER`` (903.8).
- ``CastChoices``: the record a spell carries on the stack (``GameObject.spell``): its variant,
  permission and the zone it was cast from (601.2a), then the total cost locked in (601.2f) and the
  mana spent (601.2h). A permanent spell's record passes to the permanent it becomes, as
  ``GameObject.cast_record`` (400.7d). Its targets (601.2c) are ``TargetObject`` and
  ``TargetPlayer`` values, one tuple per instance of the word "target"; modes and X join it in
  M2.7.

Everything here is Immutable: a record is replaced, never changed, as each choice is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from resolve.data.mana_cost import ManaCost
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.mana import Mana
from resolve.state.zones import Zone, ZoneKind
from resolve.values import Immutable

# --- Cast variants -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Normal(Immutable):
    """Cast the card with its normal characteristics (601.2a): a single-faced card, the front face
    of a double-faced card (712.11), the normal part of an omen or preparation card (720.3,
    722.3)."""


@dataclass(frozen=True)
class Half(Immutable):
    """Cast one half of a split card, ``index`` 0 (left) or 1 (right) (709.3)."""

    index: int


@dataclass(frozen=True)
class Fused(Immutable):
    """Cast both halves of a split card with fuse (702.102)."""


@dataclass(frozen=True)
class Back(Immutable):
    """Cast a double-faced card with its back face up: a modal double-faced card's back face
    (712.11b), or a card cast "transformed" or "converted" (712.11a)."""


class AlternativeKind(Enum):
    """The cards that have an alternative set of characteristics to cast."""

    ADVENTURE = "adventure"  # 715.3
    OMEN = "omen"  # 720.3
    PROTOTYPE = "prototype"  # 718.3
    PREPARE = "prepare"  # 722.3: never cast from the card; its copies are (722.3c)


@dataclass(frozen=True)
class Alternative(Immutable):
    """Cast the card with its alternative characteristics (715.3, 720.3, 718.3)."""

    kind: AlternativeKind


class FaceDownKind(Enum):
    """The ways of casting a card face down (708.4)."""

    MORPH = "morph"  # 702.37
    DISGUISE = "disguise"  # 702.168


@dataclass(frozen=True)
class FaceDown(Immutable):
    """Cast the card face down (708.4)."""

    kind: FaceDownKind


CastVariant = Normal | Half | Fused | Back | Alternative | FaceDown

NORMAL = Normal()


def describe_variant(variant: CastVariant) -> str:
    """The variant in words, for prompts and text interfaces (``""`` for ``NORMAL``)."""
    match variant:
        case Normal():
            return ""
        case Half(index=index):
            return "left half" if index == 0 else "right half"
        case Fused():
            return "fused"
        case Back():
            return "back face"
        case Alternative(kind=kind):
            return f"as {'an' if kind.value[0] in 'aeiou' else 'a'} {kind.value.capitalize()}"
        case FaceDown(kind=kind):
            return f"face down ({kind.value})"


# --- Cast permissions --------------------------------------------------------------------------


class CastTiming(Enum):
    """When a cast permission lets a player cast.

    - ``NORMAL``: the timing 117.1a gives the spell's type: an instant (or a spell with flash,
      702.8) whenever the player has priority, any other spell with sorcery timing.
    - ``AS_THOUGH_FLASH``: as though it had flash (601.3b); from M6.
    - ``DURING_RESOLUTION``: during the resolution of the spell or ability that allows it, ignoring
      timing (608.2g); from M2.10.
    """

    NORMAL = "normal"
    AS_THOUGH_FLASH = "as though it had flash"
    DURING_RESOLUTION = "during resolution"


@dataclass(frozen=True)
class CastPermission(Immutable):
    """A rule or effect that allows a player to cast a spell (601.3).

    ``rule`` is the CR rule behind it (the rules' own, or the rule an effect's kind follows);
    ``source`` the object whose effect grants it (``None`` for the rules' own); ``zone`` the zone
    the card is cast from; ``timing`` when (``CastTiming``). Alternative costs a permission
    requires (flashback, "without paying its mana cost", 118.9) and the zone a spell cast with it
    goes to as it leaves the stack join with their milestones (M2.10, M4, M6).
    """

    rule: str
    zone: ZoneKind
    timing: CastTiming = CastTiming.NORMAL
    source: ObjectId | None = None


FROM_HAND = CastPermission("601.3", ZoneKind.HAND)
"""The rules' permission to cast a spell from one's hand (601.3, 601.2a), with 117.1a's timing."""

COMMANDER = CastPermission("903.8", ZoneKind.COMMAND)
"""A player may cast a commander they own from the command zone (903.8)."""


# --- Targets -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetObject(Immutable):
    """An object chosen as a target (115.1): a permanent (115.2), or a spell on the stack.

    An object that changes zones becomes a new object (400.7), so a target that left the zone it
    was in when it was targeted no longer exists under this ID (608.2b).
    """

    object: ObjectId


@dataclass(frozen=True)
class TargetPlayer(Immutable):
    """A player chosen as a target (115.1)."""

    player: PlayerId


Target = TargetObject | TargetPlayer
"""An object or player chosen as a target (115.1)."""


# --- The record of a spell ---------------------------------------------------------------------


@dataclass(frozen=True)
class CastChoices(Immutable):
    """What a spell on the stack records about how it is being cast (601.2, 707.10).

    - ``variant``, ``permission``: as chosen before the card moved (601.2a, 601.3e).
    - ``cast_from``: the zone the card came from (601.2a).
    - ``targets``: the targets chosen (601.2c), one tuple per instance of the word "target", in
      the order the spell's text has them (``TargetSpec``); a tuple may be empty when the
      instance allows zero targets (115.6). Empty until chosen, and for a spell without targets.
    - ``total_cost``: the mana part of the total cost, locked in (601.2f); ``None`` until then.
    - ``mana_spent``: the mana spent to pay it (601.2h, 400.7d).
    """

    variant: CastVariant
    permission: CastPermission
    cast_from: Zone
    total_cost: ManaCost | None = None
    mana_spent: tuple[Mana, ...] = ()
    targets: tuple[tuple[Target, ...], ...] = ()

    @property
    def targeted(self) -> bool:
        """Whether the spell is targeted: at least one target was chosen (115.6)."""
        return any(self.targets)
