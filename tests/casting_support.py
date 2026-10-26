"""Script steps and lookups for tests that cast spells (601.2, 733)."""

from __future__ import annotations

from resolve.agents.scripted import Choose, Step, choose
from resolve.data.types import Color
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    Amounts,
    CastSpellOption,
    ChooseOne,
    ColorOption,
    ManaActivationOption,
    ModesOption,
    Number,
    ObjectOption,
    Option,
    PassOption,
    PlayerOption,
)
from resolve.engine.payment import PAY
from resolve.events.base import AnswerRecord
from resolve.state.game import GameState
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import FROM_HAND, NORMAL, CastPermission, CastVariant
from tests.game_fixtures import request_of


def cast(
    obj: ObjectId,
    player: PlayerId | None = None,
    variant: CastVariant = NORMAL,
    permission: CastPermission = FROM_HAND,
) -> Choose:
    """Choose to cast ``obj`` with priority (117.1a)."""
    return choose(
        CastSpellOption(obj, variant, permission), player=player, kind=DecisionKind.PRIORITY_ACTION
    )


def activate(obj: ObjectId, ability: int = 0) -> Choose:
    """601.2g: activate a mana ability while paying."""
    return choose(ActivateAbilityOption(obj, ability), kind=DecisionKind.ACTIVATE_MANA_ABILITIES)


def activate_with_priority(obj: ObjectId, ability: int = 0) -> Choose:
    """605.3a: activate a mana ability with priority."""
    return choose(ActivateAbilityOption(obj, ability), kind=DecisionKind.PRIORITY_ACTION)


def pay() -> Choose:
    """601.2g: done activating mana abilities; pay."""
    return choose(PAY, kind=DecisionKind.ACTIVATE_MANA_ABILITIES)


def counts(*amounts: int) -> Step:
    """601.2h: how many units of each class of mana to spend."""
    return Step(Amounts(amounts), kind=DecisionKind.PAY_COSTS)


def reverse(*activations: ManaActivationOption) -> Choose:
    """733.1: which of the mana abilities activated during the action to reverse."""
    return choose(*activations, kind=DecisionKind.REVERSE_MANA_ABILITIES)


def choose_targets(*targets: ObjectId | PlayerOption, player: PlayerId | None = None) -> Choose:
    """601.2c: the targets for one instance of the word "target": objects by ID, players as
    ``PlayerOption``."""
    chosen = [t if isinstance(t, PlayerOption) else ObjectOption(t) for t in targets]
    return choose(*chosen, player=player, kind=DecisionKind.CHOOSE_TARGETS)


def choose_modes(*modes: int, player: PlayerId | None = None) -> Choose:
    """601.2b, 700.2: the modes of a modal spell, by index from 0 in printed order."""
    return choose(ModesOption(modes), player=player, kind=DecisionKind.CHOOSE_MODES)


def choose_x(value: int, player: PlayerId | None = None) -> Step:
    """601.2b, 107.3a: the value announced for X."""
    return Step(Number(value), player=player, kind=DecisionKind.CHOOSE_X)


def choose_color(color: Color) -> Choose:
    """106.1a: the color of the mana an ability adds."""
    return choose(ColorOption(color), kind=DecisionKind.CHOOSE_COLOR)


def pass_(player: PlayerId | None = None) -> Choose:
    return choose(PassOption(), player=player, kind=DecisionKind.PRIORITY_ACTION)


def options(state: GameState) -> tuple[Option, ...]:
    """The options of the pending ``ChooseOne`` decision."""
    space = request_of(state).space
    assert isinstance(space, ChooseOne)
    return space.options


def records[T](state: GameState, kind: type[T]) -> list[T]:
    """Every logged record of this type, in order."""
    return [entry.record for entry in state.event_log if isinstance(entry.record, kind)]


def answered(state: GameState, kind: DecisionKind) -> int:
    """How many decisions of this kind were answered."""
    return sum(record.kind is kind for record in records(state, AnswerRecord))
