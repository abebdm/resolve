"""Priority (117): who may act, what they may do, when the stack resolves and when a step ends.

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

- Casting a spell (601.2) runs ``CastSpell``. Its caster receives priority again (117.3c); the
  passes before it stop counting once the spell is cast (117.4), but not if the attempt was
  illegal and reversed (733.2).
- When all players pass in succession with objects on the stack, the top one resolves
  (``ResolveTopOfStack``, 405.5, 608.1), and then the active player receives priority (117.3b).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

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
from resolve.engine.casting import CastSpell
from resolve.engine.mana import ActivateManaAbility
from resolve.engine.payment import mana_ability_options
from resolve.engine.resolution import ResolveTopOfStack
from resolve.engine.sba import CheckStateBasedActions
from resolve.errors import EngineError
from resolve.events.permanents import LandPlayed
from resolve.events.pipeline import ApplyEvents
from resolve.events.turn import PriorityPassed
from resolve.rules import defaults
from resolve.state.game import next_in_turn_order, players_in_game
from resolve.state.ids import PlayerId
from resolve.state.turn import TurnState
from resolve.tasks import Done, NeedDecision, Push, Task, TaskResult

if TYPE_CHECKING:
    from resolve.decisions.request import DecisionRequest
    from resolve.state.game import GameState


def current_turn(state: GameState) -> TurnState:
    """The turn in progress; ``EngineError`` before the first turn."""
    if state.turn is None:
        raise EngineError("there is no turn in progress")
    return state.turn


def priority_options(state: GameState, player: PlayerId) -> tuple[Option, ...]:
    """Everything ``player`` may do with priority right now, pass first (117.1).

    Land plays and spells come from ``defaults.land_play_options`` and ``defaults.cast_options``;
    a card in the hand is listed in hand order, other cards (commanders in the command zone)
    after them.
    """
    lands = defaults.land_play_options(state, player)  # 305.1, 116.2a
    spells = defaults.cast_options(state, player)  # 601.3, 903.8
    hand = state.player(player).hand
    options: list[Option] = [PassOption()]
    for obj in hand:
        if obj in lands:
            options.append(PlayLandOption(obj))
        options += [spell for spell in spells if spell.object == obj]
    options += [PlayLandOption(obj) for obj in lands if obj not in hand]
    options += [spell for spell in spells if spell.object not in hand]
    # 605.3a: a mana ability whenever the player has priority; 602.2, 118.3.
    options += mana_ability_options(state, player)
    return tuple(options)


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
        if state.player(player).left_game:
            # 800.4a, 800.4j: the player who would receive priority has left the game. If every
            # player still in it has passed in succession, that is all players passing (117.4);
            # otherwise priority goes to the next player in turn order still in the game.
            if all(p in turn.passed for p in players_in_game(state)):
                return self._all_passed(state)
            self.next_player = next_in_turn_order(state, player)
            self.stage = Stage.CHECK
            return self.run(state)
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
        player = request.for_player
        match request.space.chosen(answer):
            case PassOption():
                return self._pass(state, turn, player)
            case PlayLandOption(object=card):
                played = LandPlayed(player=player, card=card, rules=("305.1", "116.2a"))
                return self._acted(turn, player, ApplyEvents((played,)))
            case ActivateAbilityOption(object=source, ability=index):
                activation = ActivateManaAbility(player, source, index)
                return self._acted(turn, player, activation)
            case CastSpellOption(object=card, variant=variant, permission=permission):
                # 117.3c, 733.2: the caster receives priority again afterwards; the passes before
                # it stop counting only once the spell is cast (CastSpell clears them, 601.2i).
                cast = CastSpell(player, card, variant, permission)
                return self._acted(turn, player, cast, clears_passes=False)
            case option:
                raise EngineError(f"unexpected priority option {option!r}")

    def _all_passed(self, state: GameState) -> TaskResult:
        """117.4: all players passed in succession. With an empty stack the step ends; otherwise
        the top object resolves (405.5, 608.1), then the active player receives priority (117.3b)
        and passing starts over."""
        if not state.stack:
            return Done()
        turn = current_turn(state)
        turn.priority = None
        turn.passed.clear()
        self.next_player = None
        self.stage = Stage.CHECK
        return Push((ResolveTopOfStack(), self))

    def _acted(
        self, turn: TurnState, player: PlayerId, action: Task, *, clears_passes: bool = True
    ) -> TaskResult:
        # 117.3c: the player who acted receives priority again; 117.4: passing in succession
        # starts over.
        turn.priority = None
        if clears_passes:
            turn.passed.clear()
        self.next_player = player
        self.stage = Stage.CHECK
        return Push((action, self))

    def _pass(self, state: GameState, turn: TurnState, player: PlayerId) -> TaskResult:
        # 117.3d: the player passes; then the next player in turn order receives priority.
        everyone = all(p in (*turn.passed, player) for p in players_in_game(state))
        if everyone and state.stack:
            return self._all_passed(state)
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
