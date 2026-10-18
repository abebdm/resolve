"""Priority (117): who may act, what they may do, and when a step ends.

``PriorityRound`` runs one round of priority in a step: the active player receives priority
first (117.3a); a player who passes gives priority to the next player in turn order (117.3d);
once every player still in the game has passed in succession, the step ends if the stack is
empty, and otherwise the top of the stack resolves (117.4).

Each time a player would receive priority, state-based actions are performed first (117.5,
704.3), repeated until none apply; then waiting triggered abilities would be put on the stack
(none can exist until M4).

The options are listed in a fixed order: pass first, then each card in the player's hand in
hand order (play it as a land, or cast it), then commanders in the command zone. Actions the
engine can't perform yet are still offered, so the set of legal actions is never silently
smaller than the rules allow; choosing one raises ``NotImplementedRule`` (docs/decisions.md):

- playing a land (305.1) until M1.3;
- casting a spell (601.2) until M2.

A player who controls a land with a basic land type has its intrinsic mana ability (305.6),
which arrives in M1.3; until then building that player's options raises ``NotImplementedRule``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    AnswerValue,
    CastSpellOption,
    ChooseOne,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine.sba import CheckStateBasedActions
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.pipeline import ApplyEvents
from resolve.events.turn import PriorityPassed
from resolve.state.game import next_in_turn_order, players_in_game
from resolve.state.ids import PlayerId
from resolve.state.turn import TurnState
from resolve.tasks import NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

# 305.6: the basic land types, each giving a land the intrinsic ability to add its mana.
BASIC_LAND_TYPES = ("Plains", "Island", "Swamp", "Mountain", "Forest")
# Card types of spells (301.1, 302.1, 303.1, 304.1, 306.1, 307.1, 310.1; 308.1 for kindreds).
SPELL_TYPES = (
    CardType.ARTIFACT,
    CardType.BATTLE,
    CardType.CREATURE,
    CardType.ENCHANTMENT,
    CardType.INSTANT,
    CardType.PLANESWALKER,
    CardType.SORCERY,
)


def current_turn(state: GameState) -> TurnState:
    """The turn in progress; ``EngineError`` before the first turn."""
    if state.turn is None:
        raise EngineError("there is no turn in progress")
    return state.turn


def priority_options(state: GameState, player: PlayerId) -> tuple[Option, ...]:
    """Everything ``player`` may do with priority right now, pass first (117.1)."""
    turn = current_turn(state)
    # 117.1a, 305.1, 116.2a: sorcery-speed actions need the player's own main phase with an
    # empty stack.
    sorcery_timing = player == turn.active_player and turn.in_main_phase and not state.stack
    options: list[Option] = [PassOption()]
    for obj in state.player(player).hand:
        types = characteristics(state, obj).card_types
        if CardType.LAND in types:
            # 305.1-305.3: one land per turn (305.2a), in the player's own main phase with an
            # empty stack. 305.9: a land can't be cast, even if it has another card type.
            if sorcery_timing and turn.lands_played < 1:
                options.append(PlayLandOption(obj))
        elif _may_cast(types, sorcery_timing):
            options.append(CastSpellOption(obj))
    for obj in state.command:
        card = state.objects[obj].card
        # 903.8: a player may cast a commander they own from the command zone.
        if card is not None and card in state.player(player).commanders:
            types = characteristics(state, obj).card_types
            if CardType.LAND not in types and _may_cast(types, sorcery_timing):
                options.append(CastSpellOption(obj))
    for obj in state.battlefield:
        permanent = state.objects[obj]
        if permanent.controller != player:
            continue
        chars = characteristics(state, obj)
        if chars.is_a(CardType.LAND) and any(t in BASIC_LAND_TYPES for t in chars.subtypes):
            raise NotImplementedRule(
                "305.6: the mana abilities of lands with basic land types (roadmap M1.3)"
            )
    return tuple(options)


def _may_cast(types: tuple[CardType, ...], sorcery_timing: bool) -> bool:
    """Whether a card of these types may be cast now (117.1a): an instant whenever the player
    has priority (304.1), any other spell only with sorcery timing (301.1, 302.1, 307.1, ...).
    """
    if not any(card_type in SPELL_TYPES for card_type in types):
        return False
    return CardType.INSTANT in types or sorcery_timing


class Stage(Enum):
    """Where ``PriorityRound`` is: performing 117.5's actions, or asking."""

    CHECK = "check"
    ASK = "ask"


@dataclass(slots=True)
class PriorityRound(Task):
    """Players receive priority until all pass in succession (117.3, 117.4).

    ``next_player`` is who receives priority next (``None``: the active player, 117.3a).
    """

    next_player: PlayerId | None = None
    stage: Stage = Stage.CHECK

    def run(self, state: GameState) -> TaskResult:
        turn = current_turn(state)
        if self.stage is Stage.CHECK:
            # 117.5, 704.3: state-based actions (and, from M4, triggers) before priority.
            self.stage = Stage.ASK
            return Push((CheckStateBasedActions(), self))
        player = turn.active_player if self.next_player is None else self.next_player
        turn.priority = player
        return NeedDecision(
            player=player,
            kind=DecisionKind.PRIORITY_ACTION,
            space=ChooseOne(priority_options(state, player)),
            prompt="You have priority: take an action, or pass.",
            rules=("117.1",),
        )

    def resume(self, state: GameState, request: DecisionRequest, answer: AnswerValue) -> TaskResult:
        if not isinstance(request.space, ChooseOne) or not isinstance(answer, Pick):
            raise EngineError(f"PriorityRound can't resume with {answer!r}")
        turn = current_turn(state)
        player = request.player
        match request.space.chosen(answer):
            case PassOption():
                return self._pass(state, turn, player)
            case PlayLandOption():
                raise NotImplementedRule("305.1: playing a land (roadmap M1.3)")
            case CastSpellOption():
                raise NotImplementedRule("601.2: casting a spell (roadmap M2)")
            case option:
                raise EngineError(f"unexpected priority option {option!r}")

    def _pass(self, state: GameState, turn: TurnState, player: PlayerId) -> TaskResult:
        # 117.3d: the player passes; then the next player in turn order receives priority.
        everyone = all(p in (*turn.passed, player) for p in players_in_game(state))
        if everyone and state.stack:
            # 117.4: all players passed in succession, so the top of the stack resolves.
            raise NotImplementedRule("608.1: resolving the top object of the stack (roadmap M2)")
        turn.priority = None
        turn.passed.append(player)
        passed = ApplyEvents((PriorityPassed(player=player, rules=("117.3d",)),))
        if everyone:
            # 117.4, 500.2: all players passed in succession with the stack empty: the step or
            # phase ends.
            return Push((passed,))
        self.next_player = next_in_turn_order(state, player)
        self.stage = Stage.CHECK
        return Push((passed, self))

