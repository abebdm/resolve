"""The scenario builder: exact game states without playing a game to reach them (design.md §14).

```python
scenario = Scenario(players=3, config=GameConfig.commander_game())
scenario.life(PlayerId(1), 7)
elves = scenario.battlefield(PlayerId(0), ["Llanowar Elves"])
top, second = scenario.library(PlayerId(2), ["Forest", "Llanowar Elves"])  # top first
state = scenario.build(SomeTask())  # runs the engine to its first decision
run_script(state, choose(PlayerOption(PlayerId(2))))
```

What a scenario can set:

- the number of players, the ``GameConfig`` and the seed of the game's RNG;
- each player's life total (any integer: 0 and negative totals are states the game can reach);
- cards in any zone: libraries, hands and graveyards (added on top, listed top first), the
  battlefield and the stack (with a controller), exile and the command zone;
- which players know a hidden card (``known_to``, 400.2);
- which permanents are tapped (``tap``, 110.5), the damage marked on them (``damage``, 120.6)
  and the mana in each pool (``mana``, 106.4);
- each player's commanders (903.3), in any zone;
- the starting player (103.1), which fixes turn order; ``None`` means not chosen yet;
- with ``at(...)``, the turn in progress: its number, the active player, the phase and step, who
  receives priority next and who has already passed in succession (117.4), and the lands played
  this turn (305.2). ``build()`` then resumes the turn there.

``build(*tasks)`` runs the given tasks (``tasks[0]`` first); with ``at(...)`` the turn resumes
after them. ``at(step)`` for a step with priority resumes as a player is about to receive
priority (117.5's state-based actions first); ``at(step, begin=True)``, and any step without
priority (untap, cleanup), starts the step from its beginning, turn-based actions included.

Cards are named by their exact card name and looked up in a ``CardDatabase`` and a
``CardRegistry``: by default the fixture cards of ``tests/game_fixtures.py``
(``scenario_database()`` and ``scenario_registry()``). Objects are created
in the order the calls are made, so their IDs and timestamps (613.7d) follow that order. Every
built state is checked with ``check_invariants`` and ``check_pure_data``.
"""

from __future__ import annotations

from collections.abc import Sequence

from resolve.agents.driver import play
from resolve.agents.scripted import ScriptedAgent, ScriptStep
from resolve.cards.registry import CardRegistry
from resolve.data.cards import CardDatabase
from resolve.engine.deck import Deck, DeckCard
from resolve.engine.loop import run
from resolve.engine.priority import PriorityRound
from resolve.engine.setup import initial_state
from resolve.engine.turns import RunStep, StepStage, TakeTurn
from resolve.rules import defaults
from resolve.state.config import GameConfig
from resolve.state.game import Card, GameState, create_object, zone_list
from resolve.state.ids import CardId, ObjectId, PlayerId
from resolve.state.invariants import check_invariants, check_pure_data
from resolve.state.mana import Mana, ManaType
from resolve.state.turn import Phase, Step, TurnState, gives_priority, segment_of
from resolve.state.zones import BATTLEFIELD, COMMAND, EXILE, STACK, Zone, ZoneKind
from resolve.tasks import Task
from tests import game_fixtures


class ScenarioError(ValueError):
    """The scenario asks for something the game state can't hold."""


class Scenario:
    """Builds a ``GameState`` piece by piece; ``build`` returns it."""

    def __init__(
        self,
        players: int = 2,
        *,
        config: GameConfig | None = None,
        seed: int = 1,
        starting_player: int | None = 0,
        database: CardDatabase | None = None,
        registry: CardRegistry | None = None,
    ) -> None:
        self._state = initial_state(config or GameConfig.standard(), [Deck(())] * players, seed)
        self._database = game_fixtures.scenario_database() if database is None else database
        self._registry = game_fixtures.scenario_registry() if registry is None else registry
        self._built = False
        self._resume: tuple[Task, ...] = ()
        if starting_player is not None:
            self._state.player(PlayerId(starting_player))  # validates the seat
            self._state.starting_player = PlayerId(starting_player)

    @property
    def players(self) -> tuple[PlayerId, ...]:
        """Every player, in seating order."""
        return tuple(player.id for player in self._state.players)

    def life(self, player: PlayerId, total: int) -> Scenario:
        """Set ``player``'s life total (119)."""
        self._open().player(player).life = total
        return self

    def add(
        self,
        name: str,
        *,
        owner: PlayerId,
        zone: Zone,
        controller: PlayerId | None = None,
        known_to: Sequence[PlayerId] = (),
    ) -> ObjectId:
        """Put a new card named ``name`` on top of ``zone``; returns its object's ID.

        ``controller`` is required on the battlefield and the stack and refused elsewhere
        (108.4, 110.2). A library, hand or graveyard must be the owner's own (400.3). ``known_to``
        lists players who know the card's identity although the zone hides it (400.2).
        """
        state = self._open()
        state.player(owner)
        if zone.kind.is_per_player and zone.owner != owner:
            raise ScenarioError(f"a card owned by player {owner} can't be in the {zone} (400.3)")
        for player in known_to:
            state.player(player)
        card = self._card(name, owner)
        try:
            obj = create_object(state, card=card.id, owner=owner, zone=zone, controller=controller)
        except Exception:
            del state.cards[card.id]  # leave the scenario as it was
            raise
        obj.known_to = tuple(sorted(dict.fromkeys(known_to)))
        return obj.id

    def library(self, player: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        """Put cards on top of ``player``'s library, listed top first; returns their IDs."""
        return self._pile(Zone.library(player), player, names)

    def hand(self, player: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        """Put cards into ``player``'s hand; returns their IDs."""
        return [self.add(name, owner=player, zone=Zone.hand(player)) for name in names]

    def graveyard(self, player: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        """Put cards on top of ``player``'s graveyard, listed top first; returns their IDs."""
        return self._pile(Zone.graveyard(player), player, names)

    def battlefield(
        self, controller: PlayerId, names: Sequence[str], *, owner: PlayerId | None = None
    ) -> list[ObjectId]:
        """Put permanents onto the battlefield under ``controller`` (owned by ``owner``)."""
        owner = controller if owner is None else owner
        return [
            self.add(name, owner=owner, zone=BATTLEFIELD, controller=controller) for name in names
        ]

    def stack(
        self, controller: PlayerId, names: Sequence[str], *, owner: PlayerId | None = None
    ) -> list[ObjectId]:
        """Put cards on the stack under ``controller``, listed top first (405.2)."""
        owner = controller if owner is None else owner
        ids = [
            self.add(name, owner=owner, zone=STACK, controller=controller)
            for name in reversed(names)
        ]
        return ids[::-1]

    def exile(self, owner: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        """Put cards owned by ``owner`` into exile (406), face up."""
        return [self.add(name, owner=owner, zone=EXILE) for name in names]

    def command(self, owner: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        """Put cards owned by ``owner`` into the command zone (408)."""
        return [self.add(name, owner=owner, zone=COMMAND) for name in names]

    def commander(self, player: PlayerId, name: str, *, zone: Zone = COMMAND) -> ObjectId:
        """Make a card named ``name`` one of ``player``'s commanders (903.3), in ``zone``.

        Needs the Commander rules in the config. A commander on the battlefield or the stack is
        controlled by its owner. Like ``new_game``, the builder doesn't check whether the card
        may be a commander (legendary creature, partner for a second one: 903.3, 903.5); that is
        deck validation, in M7.
        """
        state = self._open()
        if state.config.commander is None:
            raise ScenarioError("commanders need a config with the Commander rules (903)")
        controller = player if zone.kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK) else None
        obj = self.add(name, owner=player, zone=zone, controller=controller)
        card = state.objects[obj].card
        assert card is not None
        state.player(player).commanders += (card,)
        return obj

    def tap(self, *objs: ObjectId) -> Scenario:
        """Tap these permanents (110.5); only permanents have status (110.5d)."""
        state = self._open()
        for obj in objs:
            if state.object(obj).zone.kind is not ZoneKind.BATTLEFIELD:
                raise ScenarioError(f"object {obj} isn't a permanent, so it can't be tapped")
        for obj in objs:
            state.objects[obj].tapped = True
        return self

    def damage(self, obj: ObjectId, amount: int) -> Scenario:
        """Mark ``amount`` damage on a permanent (120.3e); only permanents can have damage."""
        state = self._open()
        if state.object(obj).zone.kind is not ZoneKind.BATTLEFIELD:
            raise ScenarioError(f"object {obj} isn't a permanent, so it can't have damage")
        if amount < 0:
            raise ScenarioError("damage can't be negative")
        state.objects[obj].damage = amount
        return self

    def mana(self, player: PlayerId, *mana: ManaType) -> Scenario:
        """Add unspent mana of these types to ``player``'s mana pool (106.4), with no source."""
        self._open().player(player).mana_pool.extend(Mana(mana_type) for mana_type in mana)
        return self

    def card_of(self, obj: ObjectId) -> CardId:
        """The physical card an object of this scenario represents."""
        card = self._state.object(obj).card
        if card is None:
            raise ScenarioError(f"object {obj} isn't a card")
        return card

    def at(
        self,
        where: Phase | Step,
        *,
        active: PlayerId | None = None,
        number: int = 1,
        priority: PlayerId | None = None,
        passed: Sequence[PlayerId] = (),
        lands_played: int = 0,
        begin: bool = False,
    ) -> Scenario:
        """Put the game in turn ``number`` of ``active``, at ``where`` (a step or a main phase).

        ``active`` defaults to the starting player. ``priority`` (default: the active player)
        receives priority next, after ``passed`` have passed in succession (117.4). With
        ``begin`` (always, for untap and cleanup) the step starts from its beginning instead.
        """
        state = self._open()
        if state.starting_player is None:
            raise ScenarioError("a turn needs a starting player (103.1)")
        active = state.starting_player if active is None else active
        for player in (active, *passed, *(() if priority is None else (priority,))):
            state.player(player)
        if number < 1:
            raise ScenarioError(f"turns are numbered from 1, not {number}")
        phase, step = segment = segment_of(where)
        start = begin or not gives_priority(step)
        if start and (passed or priority is not None):
            raise ScenarioError("a step that starts from its beginning has no priority yet")
        state.turn = TurnState(
            number=number,
            active_player=active,
            phase=phase,
            step=step,
            passed=list(passed),
            lands_played=lands_played,
        )
        structure = defaults.turn_structure(state, active)
        # A structure the effects changed may lack this segment: then nothing remains.
        state.turn.segments = (
            list(structure[structure.index(segment) + 1 :]) if segment in structure else []
        )
        rest = TakeTurn(active, started=True)
        if start:
            self._resume = (RunStep(phase, step), rest)
        else:
            self._resume = (
                PriorityRound(next_player=priority),
                RunStep(phase, step, stage=StepStage.END),
                rest,
            )
        return self

    def build(self, *tasks: Task) -> GameState:
        """The finished state, checked; with tasks or a turn (``at``), run to a pause.

        Without either nothing runs and nothing is pending. Otherwise the engine runs ``tasks``
        (``tasks[0]`` first) and then the turn until a task needs a decision or the game ends;
        exceptions such as ``NotImplementedRule`` propagate. A scenario builds one state only.
        """
        state = self._open()
        self._built = True
        check_invariants(state)
        check_pure_data(state)
        tasks = (*tasks, *self._resume)
        if tasks:
            state.tasks = list(reversed(tasks))
            run(state)
            check_invariants(state)
            check_pure_data(state)
        return state

    def _open(self) -> GameState:
        if self._built:
            raise ScenarioError("this scenario has already been built")
        return self._state

    def _pile(self, zone: Zone, owner: PlayerId, names: Sequence[str]) -> list[ObjectId]:
        # The last element of a pile is its top, so the bottom card is created first.
        ids = [self.add(name, owner=owner, zone=zone) for name in reversed(names)]
        return ids[::-1]

    def _card(self, name: str, owner: PlayerId) -> Card:
        state = self._state
        deck_card = DeckCard.from_registry(self._database.get(name), self._registry)
        card = Card(CardId(len(state.cards) + 1), owner, deck_card.data, deck_card.definitions)
        state.cards[card.id] = card
        return card


def names(state: GameState, zone: Zone) -> list[str]:
    """The card names in ``zone``, in list order (for piles, bottom first: the last is the top)."""
    return [state.card_of(state.objects[obj]).data.name for obj in zone_list(state, zone)]


def run_script(state: GameState, *steps: ScriptStep) -> int:
    """Answer the next decisions with ``steps``, one each, and check every step was used.

    Returns the number of answers accepted. A step that doesn't fit what the game asks raises
    ``ScriptError``; a rejected answer raises ``InvalidAnswer``; engine errors propagate.
    """
    agent = ScriptedAgent(steps)
    accepted = play(state, agent, max_answers=len(steps))
    agent.check_finished()
    return accepted
