"""Priority (117): who may act, what they may do, and when a step ends.

``PriorityRound`` runs one round of priority in a step: the active player receives priority
first (117.3a); a player who passes gives priority to the next player in turn order (117.3d);
once every player still in the game has passed in succession, the step ends if the stack is
empty, and otherwise the top of the stack resolves (117.4).

Each time a player would receive priority, state-based actions are performed first (117.5,
704.3), repeated until none apply; then waiting triggered abilities would be put on the stack
(none can exist until M4).

The options are listed in a fixed order: pass first, then each card in the player's hand in
hand order (play it as a land, or cast it), then commanders in the command zone, then the mana
abilities of the permanents the player controls, in battlefield order and ability order.

- Playing a land (305.1) is a special action (116.2a): the land goes onto the battlefield.
- Activating a mana ability (605.3a) pays its cost and adds its mana at once (605.3b).
- After either, the same player receives priority again (117.3c), and the passes before it no
  longer count toward ending the step (117.4).

Casting a spell is offered too, so the set of legal actions is never silently smaller than the
rules allow; choosing it raises ``NotImplementedRule("601.2")`` until M2 (docs/decisions.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from resolve.cards.primitives.abilities import ActivatedManaAbility
from resolve.data.types import CardType
from resolve.decisions.kinds import DecisionKind
from resolve.decisions.spaces import (
    ActivateAbilityOption,
    AnswerValue,
    CastSpellOption,
    ChooseOne,
    Option,
    PassOption,
    Pick,
    PlayLandOption,
)
from resolve.effects.characteristics import characteristics
from resolve.engine.mana import ActivateManaAbility
from resolve.engine.sba import CheckStateBasedActions
from resolve.errors import EngineError, NotImplementedRule
from resolve.events.permanents import LandPlayed
from resolve.events.pipeline import ApplyEvents
from resolve.events.turn import PriorityPassed
from resolve.state.game import next_in_turn_order, players_in_game
from resolve.state.ids import PlayerId
from resolve.state.turn import TurnState
from resolve.tasks import NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState

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
        if state.objects[obj].controller != player:
            continue
        for index, ability in enumerate(characteristics(state, obj).abilities):
            # 605.3a: a mana ability whenever the player has priority; 602.2, 118.3.
            if isinstance(ability, ActivatedManaAbility) and ability.can_activate(
                state, obj, player
            ):
                options.append(ActivateAbilityOption(obj, index))
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
            case PlayLandOption(object=card):
                played = LandPlayed(player=player, card=card, rules=("305.1", "116.2a"))
                return self._acted(turn, player, ApplyEvents((played,)))
            case ActivateAbilityOption(object=source, ability=index):
                activation = ActivateManaAbility(player, source, index)
                return self._acted(turn, player, activation)
            case CastSpellOption():
                raise NotImplementedRule("601.2: casting a spell (roadmap M2)")
            case option:
                raise EngineError(f"unexpected priority option {option!r}")

    def _acted(self, turn: TurnState, player: PlayerId, action: Task) -> TaskResult:
        # 117.3c: the player who acted receives priority again; 117.4: passing in succession
        # starts over.
        turn.priority = None
        turn.passed.clear()
        self.next_player = player
        self.stage = Stage.CHECK
        return Push((action, self))

    def _pass(self, state: GameState, turn: TurnState, player: PlayerId) -> TaskResult:
        # 117.3d: the player passes; then the next player in turn order receives priority.
        everyone = all(p in (*turn.passed, player) for p in players_in_game(state))
        if everyone and state.stack:
            # 117.4: all players passed in succession, so the top of the stack resolves.
            raise NotImplementedRule("608.1: resolving the top object of the stack (roadmap M2)")
        turn.priority = None
        turn.passed.append(player)
        pool = tuple(state.player(player).mana_pool)
        # 106.4b: a player passing with mana in their pool announces it.
        rules = ("117.3d", "106.4b") if pool else ("117.3d",)
        passed = ApplyEvents((PriorityPassed(player=player, mana_in_pool=pool, rules=rules),))
        if everyone:
            # 117.4, 500.2: all players passed in succession with the stack empty: the step or
            # phase ends.
            return Push((passed,))
        self.next_player = next_in_turn_order(state, player)
        self.stage = Stage.CHECK
        return Push((passed, self))
