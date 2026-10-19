"""The fuzz harness: random-agent games, checked after every decision (design.md §14).

Usage::

    uv run python tools/fuzz.py                   # quick: 10 games, 2 to 6 players, both formats
    uv run python tools/fuzz.py --thorough        # the long run for verifying a milestone
    uv run python tools/fuzz.py --games 50 --seed 5000 --check-every 1
    uv run python tools/fuzz.py --deck a.txt --deck b.txt  # decks from the snapshot, cycled
    uv run python tools/fuzz.py --empty-decks     # every game ends in the first upkeep

The players get decks of basic lands (``basic_land_deck``) from the committed excerpt
``tools/excerpts/basic_lands.json``, so no snapshot is needed. The presets (``QUICK``, the
default, and ``THOROUGH``) set the number of games, the deck sizes, the concession rate and how
often the full checks run (``check_every``); explicit options override them. Games run in
``--jobs`` worker processes; the output doesn't depend on it, except for the timing. With ``--deck``, game seed ``s``
gives seat ``i`` deck ``(s + i) % len(decks)``, so a failing game is reproduced by its seed alone.

Each game is played by ``RandomAgent``s. Before every answer (with ``check_every`` N > 1, every
N answers and at the end; the bookkeeping invariants always) the harness checks:

- the state's bookkeeping invariants and that it is pure data (``resolve.state.invariants``);
- every player's view, against an oracle written out from the rules rather than the engine's
  own helpers: deeply immutable; the request only for the deciding player; the turn (number,
  active player, phase, step and priority holder, all public); every player's life, whether
  they lost, their mana pool, library count (401.2), hand and graveyard objects in order
  (402.3, 404.2) and the shared zones, with each permanent's tapped status and damage;
  card names exactly where the viewer may know them (400.2, 402.3); and only the log entries the
  viewer may see, with answers visible only to their player (design.md §7), and the redacted
  form of the others, which never shows another player's library objects (design.md §9);
- that the state survives ``copy.deepcopy`` and ``pickle`` unchanged;
- that answers outside the answer space, for another request or from another player are
  rejected and change nothing (design.md §6);

and then submits the agent's answer to the state, to a deep copy and to a pickled copy, which
must all end the same way and in equal states: a state copied mid-task resumes exactly as the
original (design.md §5). A random answer the asking task rejects must change nothing; the agent
answers again. Now and then a random player concedes instead (104.3a; ``--concessions``), in the
state and its copies alike. At the end, the game is replayed from its config, decks, seed and
recorded inputs (answers and concessions) and must reproduce the identical state (design.md
§12).

A game ends when it is over or when it reaches a ``NotImplementedRule`` for an allowed rule
(``ALLOWED_GAPS``). Any other exception, a disallowed gap, or a failed check raises
``FuzzFailure`` naming the seed. The command line prints a summary (``summary_lines``: answers
and turns per game, endings by type, lands played and mana abilities activated) and games per
second as a rough benchmark.

Exit status: 0 every game passed; 1 a game failed, or the decks couldn't be built.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import io
import multiprocessing
import os
import pickle
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from resolve.agents.base import Agent
from resolve.agents.driver import MAX_ATTEMPTS, agent_for
from resolve.agents.random_agent import RandomAgent
from resolve.agents.replay import ReplayDiverged, replay
from resolve.cards.registry import default_registry
from resolve.data.cards import CardDataError, load_card_database, load_card_excerpt
from resolve.data.decklist import DeckEntry, Decklist, DecklistError, load_decklist
from resolve.decisions.request import DecisionAnswer, DecisionRequest
from resolve.decisions.spaces import (
    Amounts,
    AnswerValue,
    ChooseNumber,
    ChooseOne,
    ChooseOrder,
    ChooseSubset,
    Distribute,
    Number,
    Order,
    Pick,
    PickMany,
)
from resolve.engine.api import new_game, pending_decision, submit, view_for
from resolve.engine.concede import concede
from resolve.engine.deck import Deck, build_deck
from resolve.engine.view import ObjectView
from resolve.errors import DeckError, InvalidAnswer, NotImplementedRule
from resolve.events.base import AnswerRecord, LogEntry
from resolve.events.cards import CardDrawn, CardsPutOnBottom
from resolve.events.game import PlayerLost
from resolve.events.mana import ManaAdded
from resolve.events.permanents import LandPlayed
from resolve.state.config import GameConfig
from resolve.state.game import GameState, players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations, mutable_parts, state_impurities
from resolve.state.rng import Rng
from resolve.state.zones import ZoneKind

# Gaps that end a fuzz game normally: casting a spell, which a random agent may choose but the
# engine can't do yet (until M2).
ALLOWED_GAPS: tuple[str, ...] = ("601.2",)
# A game that hasn't ended after this many answers is reported as a failure (a runaway game).
MAX_ANSWERS = 10_000


class FuzzFailure(AssertionError):
    """A fuzz game broke a check. The message says which game and how to reproduce it."""


@dataclass(frozen=True)
class FuzzResult:
    """How one fuzz game ended.

    - ``answers``: answers the engine accepted; ``rejected``: random answers it rejected.
    - ``gap``: the ``NotImplementedRule`` message the game stopped at, or ``None`` if it ended.
    - ``state``: the final state.
    """

    answers: int
    rejected: int
    gap: str | None
    state: GameState


# What submitting an answer did: accepted, rejected (with the message) or stopped at a gap.
Outcome = tuple[str, str]


def _submit(state: GameState, answer: DecisionAnswer) -> Outcome:
    try:
        submit(state, answer)
    except InvalidAnswer as error:
        return ("rejected", str(error))
    except NotImplementedRule as gap:
        return ("gap", str(gap))
    return ("accepted", "")


def _concede(state: GameState, player: PlayerId) -> Outcome:
    try:
        concede(state, player)
    except InvalidAnswer as error:
        return ("rejected", str(error))
    except NotImplementedRule as gap:
        return ("gap", str(gap))
    return ("accepted", "")


def _pickled(state: GameState) -> GameState:
    restored: GameState = pickle.loads(pickle.dumps(state))
    return restored


def _expected_name(state: GameState, obj_id: ObjectId, viewer: PlayerId) -> str | None:
    """The name ``viewer`` should see for an object, worked out from the rules.

    Written out here rather than calling the engine's ``is_known_to``, so the check is
    independent of the code it checks: public zones show every card (400.2, 404.2, 406.3);
    a hand shows its cards to its owner (402.3) and to players who know them (400.2).
    """
    obj = state.objects[obj_id]
    name = state.card_of(obj).data.name
    if obj.zone.kind is ZoneKind.HAND:
        return name if viewer == obj.owner or viewer in obj.known_to else None
    return name


@dataclass
class CheckedLog:
    """The event log as a game's last full check verified it, so the next walks only what's new.

    The log only grows (design.md §7) and the full checks verify that each entry is deeply
    immutable when they first see it, so an entry stays verified while the log still holds that
    same object. ``entries`` is the log as last checked; ``visible`` is each player's expected
    view of it. ``state_problems`` updates both, and reports any checked entry that was replaced
    or removed. Without it, every check walks the whole log, which makes the checks of a long
    game cost time quadratic in its length.
    """

    entries: list[LogEntry] = field(default_factory=list["LogEntry"])
    visible: dict[PlayerId, list[LogEntry]] = field(default_factory=dict[PlayerId, list[LogEntry]])

    def unchanged(self, log: list[LogEntry]) -> int:
        """How many of the checked entries are still the first entries of ``log``."""
        count = min(len(self.entries), len(log))
        for index in range(count):
            if log[index] is not self.entries[index]:
                return index
        return count


def view_problems(
    state: GameState,
    viewer: PlayerId,
    *,
    start: int = 0,
    visible: list[LogEntry] | None = None,
) -> list[str]:
    """Everything ``view_for(state, viewer)`` shows wrongly (design.md §9).

    With ``start``, the event log's first ``start`` entries were checked already and
    ``visible`` holds the viewer's expected view of them; only the later entries are checked,
    and ``visible`` is extended with them.
    """
    view = view_for(state, viewer)
    where = f"player {viewer}'s view"
    if visible is None:
        visible = []
    problems = mutable_parts(dataclasses.replace(view, log=()), f"view_for({viewer})")
    for index in range(len(visible), len(view.log)):
        problems += mutable_parts(view.log[index], f"view_for({viewer}).log[{index}]")
    request = state.pending
    expected_request = request if request is not None and request.player == viewer else None
    if view.request != expected_request:
        problems.append(f"{where} holds the wrong request")
    expected_waiting = None if request is None else (request.player, request.kind)
    waiting = None if view.waiting_for is None else (view.waiting_for.player, view.waiting_for.kind)
    if waiting != expected_waiting:
        problems.append(f"{where} says it is waiting for {waiting}, not {expected_waiting}")
    if view.result != state.result or view.starting_player != state.starting_player:
        problems.append(f"{where} misreports the result or the starting player")
    turn = state.turn
    expected_turn = None
    if turn is not None:
        expected_turn = (turn.number, turn.active_player, turn.phase, turn.step, turn.priority)
    shown_turn = None
    if view.turn is not None:
        shown = view.turn
        shown_turn = (shown.number, shown.active_player, shown.phase, shown.step, shown.priority)
    if shown_turn != expected_turn:
        problems.append(f"{where} shows the turn as {shown_turn}, not {expected_turn}")

    def compare(shown: tuple[ObjectView, ...], actual: list[ObjectId], zone: str) -> None:
        # Hands may be counted (402.3) and public piles keep their order (404.2, 405.2).
        if [obj.id for obj in shown] != actual:
            problems.append(f"{where} shows the wrong objects in {zone}")
            return
        for obj in shown:
            if obj.name != _expected_name(state, obj.id, viewer):
                problems.append(f"{where} of object {obj.id} is wrong")
            if obj.tapped != state.objects[obj.id].tapped:  # 110.5: status is public
                problems.append(f"{where} misreports whether object {obj.id} is tapped")
            if obj.damage != state.objects[obj.id].damage:  # 120.6: marked damage is public
                problems.append(f"{where} misreports the damage on object {obj.id}")

    if [summary.id for summary in view.players] != [player.id for player in state.players]:
        problems.append(f"{where} lists the wrong players")
    for summary, player in zip(view.players, state.players, strict=False):
        if summary.life != player.life:
            problems.append(f"{where} shows player {player.id} at the wrong life total")
        if summary.lost != player.lost or summary.left_game != player.left_game:
            problems.append(f"{where} misreports whether player {player.id} lost")
        if summary.mana_pool != tuple(player.mana_pool):
            problems.append(f"{where} misreports player {player.id}'s mana pool")
        if summary.library_size != len(player.library):  # 401.2: only a count
            problems.append(f"{where} miscounts player {player.id}'s library")
        compare(summary.hand, player.hand, f"player {player.id}'s hand")
        compare(summary.graveyard, player.graveyard, f"player {player.id}'s graveyard")
    compare(view.battlefield, state.battlefield, "the battlefield")
    compare(view.stack, state.stack, "the stack")
    compare(view.exile, state.exile, "exile")
    compare(view.command, state.command, "the command zone")

    # design.md §7: each entry is shown to the players it names (None: everyone), and an answer
    # only to the player who gave it. Other players see an entry's redacted form, if it has one.
    for entry in state.event_log[start:]:
        if entry.visible_to is None or viewer in entry.visible_to:
            shown = entry
        elif entry.redacted is not None:
            shown = LogEntry(entry.index, entry.redacted, None)
        else:
            continue
        visible.append(shown)
        # design.md §9: library object IDs survive shuffles, so no other player sees them.
        record = shown.record
        if isinstance(record, CardDrawn) and record.player != viewer and record.drawn_from:
            problems.append(f"log entry {entry.index} shows {where} a drawn library card")
        if isinstance(record, CardsPutOnBottom) and record.player != viewer and record.cards:
            problems.append(f"log entry {entry.index} shows {where} the bottomed cards")
    if view.log != tuple(visible):
        problems.append(f"{where} shows the wrong log entries")
    for entry in state.event_log[start:]:
        record = entry.record
        if isinstance(record, AnswerRecord) and entry.visible_to != (record.player,):
            problems.append(f"log entry {entry.index} shows an answer to other players")
    return problems


def state_problems(state: GameState, checked: CheckedLog | None = None) -> list[str]:
    """Everything wrong with ``state`` and the views built from it.

    With ``checked`` (updated here), log entries an earlier call verified aren't walked again.
    """
    problems = invariant_violations(state)
    start = 0
    if checked is not None:
        start = checked.unchanged(state.event_log)
        if start < len(checked.entries):
            problems.append(
                f"state.event_log[{start}] was replaced or removed after it was logged "
                "(design.md §7: the log only grows)"
            )
            start = 0
    problems += state_impurities(state, log_from=start)
    for player in state.players:
        visible = [] if checked is None or start == 0 else checked.visible[player.id]
        problems += view_problems(state, player.id, start=start, visible=visible)
        if checked is not None:
            checked.visible[player.id] = visible
    if checked is not None:
        checked.entries = list(state.event_log)
    return problems


def invalid_answers(
    request: DecisionRequest, players: int, valid: AnswerValue
) -> list[DecisionAnswer]:
    """Answers that must be rejected: another request, another player, outside the space.

    ``valid`` is a value inside the request's space (the agent's own answer), so the answers for
    another request or from another player are rejected only for that reason.
    """

    def answer(value: AnswerValue) -> DecisionAnswer:
        return DecisionAnswer(request.id, request.player, value)

    wrong_type: AnswerValue = Pick(0) if isinstance(request.space, ChooseNumber) else Number(0)
    wrong: list[DecisionAnswer] = [
        DecisionAnswer(request.id + 1, request.player, valid),
        DecisionAnswer(request.id - 1, request.player, valid),
        answer(wrong_type),
    ]
    if players > 1:
        other = PlayerId((request.player + 1) % players)
        wrong.append(DecisionAnswer(request.id, other, valid))
    match request.space:
        case ChooseOne(options=options):
            wrong += [answer(Pick(len(options))), answer(Pick(-1)), answer(Pick(True))]
        case ChooseSubset(options=options, minimum=minimum, maximum=maximum):
            wrong.append(answer(PickMany((len(options),))))
            if maximum < len(options):
                wrong.append(answer(PickMany(tuple(range(maximum + 1)))))
            if minimum > 0:
                wrong.append(answer(PickMany(())))
            if len(options) >= 2:
                wrong.append(answer(PickMany((1, 0))))
        case ChooseOrder(options=options):
            wrong += [answer(Order(())), answer(Order(tuple(range(len(options) + 1))))]
        case ChooseNumber(minimum=minimum, maximum=maximum):
            wrong.append(answer(Number(minimum - 1)))
            if maximum is not None:
                wrong.append(answer(Number(maximum + 1)))
        case Distribute(recipients=recipients, total=total):
            wrong += [
                answer(Amounts((total,) * (len(recipients) + 1))),
                answer(Amounts((total + 1,) + (0,) * (len(recipients) - 1))),
            ]
        case _:
            pass
    return wrong


def fuzz_run(
    make_state: Callable[[], GameState],
    agents: Sequence[Agent],
    *,
    describe: str,
    allowed_gaps: Sequence[str] = ALLOWED_GAPS,
    max_answers: int = MAX_ANSWERS,
    check_copies: bool = True,
    probe_invalid: bool = True,
    concession_chance: int = 0,
    concession_seed: int = 0,
    check_every: int = 1,
) -> FuzzResult:
    """Play the game ``make_state()`` starts with ``agents`` (one per seat), checking it.

    ``make_state`` is called again for the replay, and must start the same game each time.
    ``describe`` names the game in failure messages (for example, how to reproduce it).
    With ``concession_chance`` N > 0, before each decision a player still in the game concedes
    with probability 1/N (104.3a), drawn from ``Rng.from_seed(concession_seed)``; the state's
    copies concede too and must end up equal.

    With ``check_every`` N > 1, the full checks (``state_problems``, the copies, the invalid
    answers, and that a rejected answer changed nothing) run only while the number of accepted
    answers is a multiple of N, and on the final state; the bookkeeping invariants
    (``invariant_violations``) and the replay are still checked for every game. Most full checks
    walk, copy or compare the whole state, event log included, so their cost grows with the
    game; long games need N > 1 to finish in reasonable time. A rejected answer that changed the
    state between full checks still fails the replay, which never submits it.
    """
    if check_every < 1:
        raise ValueError("check_every must be at least 1")

    def fail(problem: str) -> FuzzFailure:
        return FuzzFailure(f"{describe}: {problem}")

    checked = CheckedLog()

    def check(state: GameState, when: str) -> None:
        problems = state_problems(state, checked)
        if problems:
            raise fail(f"{when}:\n" + "\n".join(f"- {p}" for p in problems))

    def allowed(gap: str) -> bool:
        return gap.split(": ", 1)[0] in allowed_gaps

    try:
        state = make_state()
        gap: str | None = None
    except NotImplementedRule as error:
        raise fail(f"starting the game reached {error}") from error

    answers = rejected = in_a_row = 0
    concessions = Rng.from_seed(concession_seed)
    try:
        while gap is None:
            request = pending_decision(state)
            full = request is None or answers % check_every == 0
            if full:
                check(state, f"after {answers} answers")
            elif problems := invariant_violations(state):
                raise fail(f"after {answers} answers:\n" + "\n".join(f"- {p}" for p in problems))
            if request is None:
                break
            copying = check_copies and full
            if concession_chance > 0 and concessions.randbelow(concession_chance) == 0:
                in_game = players_in_game(state)
                player = in_game[concessions.randbelow(len(in_game))]
                copies = [copy.deepcopy(state), _pickled(state)] if copying else []
                outcome = _concede(state, player)
                for name, other in zip(("deep copy", "pickled copy"), copies, strict=False):
                    if _concede(other, player) != outcome or other != state:
                        raise fail(f"conceding for player {player} differs in the {name}")
                if outcome[0] == "gap":
                    if not allowed(outcome[1]):
                        raise fail(f"the game reached a gap that isn't allowed: {outcome[1]}")
                    gap = outcome[1]
                continue
            if answers >= max_answers:
                raise fail(f"the game didn't end within {max_answers} answers")
            snapshot = pickle.dumps(state) if full else None
            if copying:
                if copy.deepcopy(state) != state:
                    raise fail(f"a deep copy differs from the state after {answers} answers")
                if _pickled(state) != state:
                    raise fail(f"a pickled copy differs from the state after {answers} answers")
            agent = agent_for(agents, request.player)
            answer = agent.decide(view_for(state, request.player), request)
            if probe_invalid and snapshot is not None:
                before = pickle.loads(snapshot)
                for bad in invalid_answers(request, len(state.players), answer.value):
                    outcome = _submit(state, bad)
                    if outcome[0] != "rejected":
                        raise fail(f"the invalid answer {bad} was {outcome[0]}")
                    if state != before:
                        raise fail(f"the rejected answer {bad} changed the state")
            copies = [copy.deepcopy(state), _pickled(state)] if copying else []
            outcome = _submit(state, answer)
            for name, other in zip(("deep copy", "pickled copy"), copies, strict=False):
                other_outcome = _submit(other, answer)
                if other_outcome != outcome:
                    raise fail(
                        f"answer {answer} gave {outcome} but the {name} gave {other_outcome}"
                    )
                if other != state:
                    raise fail(f"after answer {answer} the {name} differs from the state")
            match outcome:
                case ("rejected", _):
                    rejected += 1
                    in_a_row += 1
                    if in_a_row >= MAX_ATTEMPTS:
                        raise fail(f"{MAX_ATTEMPTS} random answers in a row were rejected")
                    if snapshot is not None and state != pickle.loads(snapshot):
                        raise fail(f"the rejected answer {answer} changed the state")
                case ("accepted", _):
                    answers += 1
                    in_a_row = 0
                case (_, message):
                    answers += 1
                    if not allowed(message):
                        raise fail(f"the game reached a gap that isn't allowed: {message}")
                    gap = message
    except FuzzFailure:
        raise
    except Exception as error:
        raise fail(f"{type(error).__name__}: {error}") from error

    _check_replay(make_state, state, gap, fail)
    return FuzzResult(answers, rejected, gap, state)


def _check_replay(
    make_state: Callable[[], GameState],
    state: GameState,
    gap: str | None,
    fail: Callable[[str], FuzzFailure],
) -> None:
    """Replaying the recorded inputs from the start (answers and concessions, in order) must
    reproduce ``state`` (design.md §12)."""
    again = make_state()
    replay_gap: str | None = None
    try:
        replay(again, state.event_log)
    except NotImplementedRule as error:
        replay_gap = str(error)
    except ReplayDiverged as error:
        raise fail(f"the replay ended differently: {error}") from error
    except Exception as error:
        raise fail(f"the replay failed: {type(error).__name__}: {error}") from error
    if replay_gap != gap:
        raise fail(f"the replay ended differently: {replay_gap!r} instead of {gap!r}")
    if again != state:
        raise fail("the replay doesn't reproduce the identical state")


def fuzz_game(
    config: GameConfig,
    decks: Sequence[Deck],
    seed: int,
    *,
    agent_seed: int | None = None,
    allowed_gaps: Sequence[str] = ALLOWED_GAPS,
    max_answers: int = MAX_ANSWERS,
    check_copies: bool = True,
    probe_invalid: bool = True,
    concession_chance: int = 0,
    check_every: int = 1,
) -> FuzzResult:
    """Fuzz one game of ``new_game(config, decks, seed)``; the options are ``fuzz_run``'s.

    Seat ``i`` is played by ``RandomAgent(agent_seed + i)``; ``agent_seed`` defaults to ``seed``.
    """
    base = seed if agent_seed is None else agent_seed
    agents = [RandomAgent((base + seat) % 2**64) for seat in range(len(decks))]
    commander = " --commander" if config.commander is not None else ""
    describe = (
        f"game seed {seed}, {len(decks)} players{commander} "
        f"(reproduce: uv run python tools/fuzz.py --games 1 --seed {seed} "
        f"--players {len(decks)}{commander} and the run's other options)"
    )
    return fuzz_run(
        lambda: new_game(config, decks, seed),
        agents,
        describe=describe,
        allowed_gaps=allowed_gaps,
        max_answers=max_answers,
        check_copies=check_copies,
        probe_invalid=probe_invalid,
        concession_chance=concession_chance,
        concession_seed=seed,
        check_every=check_every,
    )


# --- The summary -------------------------------------------------------------------------------

# How a game ended, as the summary counts it (``ending``).
DECKED = "decked"
LIFE_TOTAL = "life total"
CONCESSION = "concession"
DRAW = "draw"
RULES_GAP = "rules gap"
ENDINGS = (DECKED, LIFE_TOTAL, CONCESSION, DRAW, RULES_GAP)
# The rule a player lost by (``PlayerLost.rules[0]``), for each ending.
_LOSSES = {"704.5b": DECKED, "704.5a": LIFE_TOTAL, "104.3a": CONCESSION}


def ending(result: FuzzResult) -> str:
    """How a fuzz game ended: one of ``ENDINGS``, or ``"other (<rule>)"``.

    A game stopped at an allowed gap ended at a ``RULES_GAP``. A game over with no winner is a
    ``DRAW`` (104.4a), however the players lost. Otherwise the game is named after how the last
    player to lose lost: drawing from an empty library (704.5b), 0 or less life (704.5a), or
    conceding (104.3a). A loss by any other rule is reported as ``"other (<rule>)"``, and a win
    without a loss (none is possible yet) as ``"other (no loss)"``.
    """
    if result.gap is not None:
        return RULES_GAP
    outcome = result.state.result
    if outcome is None:
        raise ValueError("the game is neither over nor stopped at a gap")
    if outcome.is_draw:
        return DRAW
    losses = [e.record for e in result.state.event_log if isinstance(e.record, PlayerLost)]
    if not losses:
        return "other (no loss)"
    rule = losses[-1].rules[0]
    return _LOSSES.get(rule, f"other ({rule})")


@dataclass(frozen=True)
class GameStats:
    """What one fuzz game exercised, for the summary.

    - ``answers``, ``rejected``: answers the engine accepted and random answers it rejected.
    - ``turns``: the number of the last turn that began (0 if the game ended before turn 1).
    - ``ending``: how it ended (``ending``).
    - ``lands_played``: lands played (``LandPlayed``, 305.1).
    - ``mana_abilities``: mana abilities activated, counted by the mana they added
      (``ManaAdded``, 605.3a, 106.4).
    """

    answers: int
    rejected: int
    turns: int
    ending: str
    lands_played: int
    mana_abilities: int

    @staticmethod
    def of(result: FuzzResult) -> GameStats:
        """The statistics of a finished fuzz game."""
        state = result.state
        records = [entry.record for entry in state.event_log]
        return GameStats(
            answers=result.answers,
            rejected=result.rejected,
            turns=0 if state.turn is None else state.turn.number,
            ending=ending(result),
            lands_played=sum(isinstance(record, LandPlayed) for record in records),
            mana_abilities=sum(isinstance(record, ManaAdded) for record in records),
        )


def _spread(values: Sequence[int]) -> str:
    return f"min {min(values)}, average {sum(values) / len(values):.1f}, max {max(values)}"


def summary_lines(games: Sequence[GameStats]) -> list[str]:
    """The summary of a fuzz run, one line per item; there must be at least one game.

    Every ending in ``ENDINGS`` is listed, in that order, even if no game ended that way; other
    endings follow, sorted.
    """
    endings = Counter(game.ending for game in games)
    names = [*ENDINGS, *sorted(name for name in endings if name not in ENDINGS)]
    answers = [game.answers for game in games]
    return [
        f"{len(games)} games passed: {sum(answers)} answers accepted, "
        f"{sum(game.rejected for game in games)} rejected.",
        f"Answers per game: {_spread(answers)}.",
        f"Turns per game: {_spread([game.turns for game in games])}.",
        "Endings: " + ", ".join(f"{name} x{endings[name]}" for name in names) + ".",
        f"Played: {sum(game.lands_played for game in games)} lands, "
        f"{sum(game.mana_abilities for game in games)} mana abilities activated.",
    ]


# --- The command line --------------------------------------------------------------------------

# The default decks: the five basic lands, copied from the Scryfall snapshot into an excerpt that
# is committed (tools/card_excerpt.py), so no snapshot is needed.
BASIC_LANDS_EXCERPT = Path(__file__).resolve().parent / "excerpts" / "basic_lands.json"
BASIC_LAND_NAMES = ("Plains", "Island", "Swamp", "Mountain", "Forest")
# Copies of each basic land in a deck, when none are given: 40 cards.
DEFAULT_COPIES = 8


@dataclass(frozen=True)
class Preset:
    """The command line's defaults for a run's length and checks; explicit options override them.

    - ``games``: how many games.
    - ``copies``: the basic-land decks, as copies of each basic land: one deck per number, cycled
      among the seats like ``--deck`` files (8 and 4: 40- and 20-card decks).
    - ``concessions``: before each decision a player concedes 1 time in this many (104.3a). The
      number of decisions per turn grows with the square of the player count, so in multiplayer
      games concessions come long before decking (704.5b); the smaller decks deck out first.
    - ``check_every``: the full checks run every this many answers (``fuzz_run``).
    """

    games: int
    copies: tuple[int, ...]
    concessions: int
    check_every: int


# The default run: quick, for the checks an agent or a developer runs while working. One game of
# each player count (2 to 6) in each format, checked every 10 answers; 40- and 10-card decks, so
# that some games end by decking.
QUICK = Preset(games=10, copies=(8, 2), concessions=200, check_every=10)
# ``--thorough``: the long run for verifying a milestone by hand. Ten rounds of the player counts
# and formats, rarer concessions so that longer games and more decking happen, and every check
# before every decision.
THOROUGH = Preset(games=100, copies=(8, 4), concessions=500, check_every=1)


def basic_land_deck(copies: int = DEFAULT_COPIES, excerpt: Path = BASIC_LANDS_EXCERPT) -> Deck:
    """A deck of ``copies`` of each basic land, Plains to Forest, from the excerpt."""
    decklist = Decklist(
        mainboard=tuple(DeckEntry(copies, name) for name in BASIC_LAND_NAMES),
        name=f"{copies * len(BASIC_LAND_NAMES)} basic lands",
    )
    return build_deck(decklist, load_card_excerpt(excerpt), default_registry())


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status described in the module docstring."""
    parser = argparse.ArgumentParser(description="Fuzz the engine with random-agent games.")
    parser.add_argument(
        "--thorough",
        action="store_true",
        help=f"the long run for verifying a milestone: {THOROUGH.games} games, concessions 1 in "
        f"{THOROUGH.concessions}, full checks before every decision",
    )
    parser.add_argument(
        "--games", type=int, default=None, help=f"number of games (default {QUICK.games})"
    )
    parser.add_argument("--seed", type=int, default=0, help="seed of the first game")
    parser.add_argument(
        "--players", type=int, nargs="*", default=[2, 3, 4, 5, 6], help="player counts to cycle"
    )
    parser.add_argument(
        "--format",
        choices=("both", "standard", "commander"),
        default="both",
        help="which game formats to cycle",
    )
    parser.add_argument("--commander", action="store_true", help="same as --format commander")
    decks = parser.add_mutually_exclusive_group()
    decks.add_argument(
        "--deck",
        type=Path,
        action="append",
        default=[],
        help="decklists to cycle, from the snapshot (default: basic lands, see --copies)",
    )
    decks.add_argument("--empty-decks", action="store_true", help="give every player an empty deck")
    decks.add_argument(
        "--copies",
        type=int,
        nargs="+",
        default=None,
        metavar="N",
        help="basic-land decks of N of each basic land, one per N, cycled among the seats "
        f"(default {' '.join(map(str, QUICK.copies))})",
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="card data snapshot directory")
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        metavar="N",
        help="games played at once, in worker processes (default: the number of CPUs)",
    )
    parser.add_argument(
        "--concessions",
        type=int,
        default=None,
        metavar="N",
        help=f"a player concedes before a decision 1 time in N (0: never; default "
        f"{QUICK.concessions})",
    )
    parser.add_argument(
        "--check-every",
        type=int,
        default=None,
        metavar="N",
        help=f"run the full checks every N answers (1: before every decision; default "
        f"{QUICK.check_every})",
    )
    args = parser.parse_args(argv)
    preset = THOROUGH if args.thorough else QUICK
    run = Preset(
        games=preset.games if args.games is None else args.games,
        copies=preset.copies if args.copies is None else tuple(args.copies),
        concessions=preset.concessions if args.concessions is None else args.concessions,
        check_every=preset.check_every if args.check_every is None else args.check_every,
    )
    if min(run.copies) < 0:
        parser.error("--copies can't be negative")
    if run.games < 1 or not args.players or min(args.players) < 2:
        parser.error("need at least one game and player counts of at least 2 (100.1)")
    if run.check_every < 1 or run.concessions < 0 or args.jobs < 1:
        parser.error("--check-every and --jobs must be at least 1, --concessions at least 0")

    fmt = "commander" if args.commander else args.format
    configs = {
        "both": [GameConfig.standard(), GameConfig.commander_game()],
        "standard": [GameConfig.standard()],
        "commander": [GameConfig.commander_game()],
    }[fmt]
    try:
        if args.empty_decks:
            pool, deck_names, deck_options = [Deck(())], "empty", "--empty-decks"
        elif args.deck:
            pool = _load_decks(args.deck, args.data_dir)
            deck_names = ", ".join(str(path) for path in args.deck)
            deck_options = " ".join(f'--deck "{path}"' for path in args.deck)
        else:
            deck_options = "--copies " + " ".join(str(copies) for copies in run.copies)
            pool = [basic_land_deck(copies) for copies in run.copies]
            sizes = " and ".join(str(copies * len(BASIC_LAND_NAMES)) for copies in run.copies)
            deck_names = f"{sizes} basic lands ({BASIC_LANDS_EXCERPT.name})"
            if len(pool) > 1:
                deck_names += ", cycled among the seats"
    except (CardDataError, DecklistError, DeckError, OSError) as error:
        print(f"error: {error}")
        return 1

    specs: list[GameSpec] = []
    for game in range(run.games):
        seed: int = args.seed + game
        players: int = args.players[game % len(args.players)]
        config = configs[(game // len(args.players)) % len(configs)]
        decks_now = tuple(pool[(seed + seat) % len(pool)] for seat in range(players))
        specs.append(GameSpec(config, decks_now, seed, run.concessions, run.check_every))
    jobs = min(args.jobs, len(specs))
    started = time.perf_counter()
    checks = "every answer" if run.check_every == 1 else f"every {run.check_every} answers"
    concessions = "never" if run.concessions == 0 else f"1 decision in {run.concessions}"
    print(
        f"Run: {'thorough' if args.thorough else 'quick'} preset; decks: {deck_names}; "
        f"concessions: {concessions}; full checks {checks}.",
        flush=True,
    )

    def progress(done: int) -> None:
        # Long runs say how far they are (no timing, so the output is the same for any --jobs).
        if len(specs) > QUICK.games and done % 10 == 0 and done < len(specs):
            print(f"{done} of {len(specs)} games passed...", flush=True)

    outcomes = _play_all(specs, jobs, progress)
    failures = [outcome for outcome in outcomes if isinstance(outcome, str)]
    if failures:
        print(f"FAILED: {failures[0]}")
        print(
            f"This run's options: {deck_options} --concessions {run.concessions} "
            f"--check-every {run.check_every}"
        )
        return 1
    games = [outcome for outcome in outcomes if isinstance(outcome, GameStats)]
    formats = Counter(
        "commander" if spec.config.commander is not None else "standard" for spec in specs
    )
    elapsed = time.perf_counter() - started
    print("\n".join(summary_lines(games)))
    print("Formats: " + ", ".join(f"{name} x{count}" for name, count in sorted(formats.items())))
    print(
        f"{run.games / elapsed:.2f} games per second, {elapsed:.0f} seconds in all "
        f"({jobs} {'job' if jobs == 1 else 'jobs'})."
    )
    return 0


@dataclass(frozen=True)
class GameSpec:
    """One game of a command-line run, as sent to a worker process."""

    config: GameConfig
    decks: tuple[Deck, ...]
    seed: int
    concessions: int
    check_every: int


def play_spec(spec: GameSpec) -> GameStats | str:
    """Play and check one game: its statistics, or the failure's message."""
    try:
        result = fuzz_game(
            spec.config,
            spec.decks,
            spec.seed,
            concession_chance=spec.concessions,
            check_every=spec.check_every,
        )
    except FuzzFailure as failure:
        return str(failure)
    return GameStats.of(result)


def _play_all(
    specs: Sequence[GameSpec], jobs: int, progress: Callable[[int], None]
) -> list[GameStats | str]:
    """Play the games in order, stopping at the first failure; with ``jobs`` > 1, in that many
    worker processes, which doesn't change any game (each depends only on its spec).
    ``progress`` is called with the number of games done, in order, after each one."""
    outcomes: list[GameStats | str] = []
    if jobs <= 1:
        for spec in specs:
            outcomes.append(play_spec(spec))
            if isinstance(outcomes[-1], str):
                break
            progress(len(outcomes))
        return outcomes
    # "spawn" is the only start method on Windows; using it everywhere keeps runs alike.
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=jobs, mp_context=context) as pool:
        for outcome in pool.map(play_spec, specs):
            outcomes.append(outcome)
            if isinstance(outcome, str):
                pool.shutdown(wait=False, cancel_futures=True)
                break
            progress(len(outcomes))
    return outcomes


def _load_decks(paths: Sequence[Path], data_dir: Path | None) -> list[Deck]:
    database = load_card_database(data_dir)
    registry = default_registry()
    return [build_deck(load_decklist(path), database, registry) for path in paths]


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card or path name; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
