"""The fuzz harness: random-agent games, checked after every decision (design.md §14).

Usage::

    uv run python tools/fuzz.py                       # 200 games, 2 to 6 players, both formats
    uv run python tools/fuzz.py --games 1000 --seed 5000
    uv run python tools/fuzz.py --deck a.txt --deck b.txt  # decks from the snapshot, cycled

With ``--deck``, game seed ``s`` gives seat ``i`` deck ``(s + i) % len(decks)``, so a failing
game is reproduced by its seed alone.

Each game is played by ``RandomAgent``s. Before every answer the harness checks:

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
``FuzzFailure`` naming the seed. The command line prints games per second as a rough
benchmark.

Exit status: 0 every game passed; 1 a game failed, or the decks couldn't be built.
"""

from __future__ import annotations

import argparse
import copy
import io
import pickle
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from resolve.agents.base import Agent
from resolve.agents.driver import MAX_ATTEMPTS, agent_for
from resolve.agents.random_agent import RandomAgent
from resolve.agents.replay import ReplayDiverged, replay
from resolve.cards.registry import default_registry
from resolve.data.cards import CardDataError, load_card_database
from resolve.data.decklist import DecklistError, load_decklist
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
from resolve.state.config import GameConfig
from resolve.state.game import GameState, players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.invariants import invariant_violations, mutable_parts, state_impurities
from resolve.state.rng import Rng
from resolve.state.zones import ZoneKind

# Gaps that end a fuzz game normally: casting a spell, which a random agent may choose but the
# engine can't do yet (until M2).
ALLOWED_GAPS: tuple[str, ...] = ("601.2",)
# By default, before each decision a player concedes with probability 1 in this (104.3a).
DEFAULT_CONCESSION_CHANCE = 200
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


def view_problems(state: GameState, viewer: PlayerId) -> list[str]:
    """Everything ``view_for(state, viewer)`` shows wrongly (design.md §9)."""
    view = view_for(state, viewer)
    where = f"player {viewer}'s view"
    problems = mutable_parts(view, f"view_for({viewer})")
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
    visible: list[LogEntry] = []
    for entry in state.event_log:
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
    for entry in state.event_log:
        record = entry.record
        if isinstance(record, AnswerRecord) and entry.visible_to != (record.player,):
            problems.append(f"log entry {entry.index} shows an answer to other players")
    return problems


def state_problems(state: GameState) -> list[str]:
    """Everything wrong with ``state`` and the views built from it."""
    problems = invariant_violations(state) + state_impurities(state)
    for player in state.players:
        problems += view_problems(state, player.id)
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
) -> FuzzResult:
    """Play the game ``make_state()`` starts with ``agents`` (one per seat), checking it.

    ``make_state`` is called again for the replay, and must start the same game each time.
    ``describe`` names the game in failure messages (for example, how to reproduce it).
    With ``concession_chance`` N > 0, before each decision a player still in the game concedes
    with probability 1/N (104.3a), drawn from ``Rng.from_seed(concession_seed)``; the state's
    copies concede too and must end up equal.
    """

    def fail(problem: str) -> FuzzFailure:
        return FuzzFailure(f"{describe}: {problem}")

    def check(state: GameState, when: str) -> None:
        problems = state_problems(state)
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
            check(state, f"after {answers} answers")
            request = pending_decision(state)
            if request is None:
                break
            if concession_chance > 0 and concessions.randbelow(concession_chance) == 0:
                in_game = players_in_game(state)
                player = in_game[concessions.randbelow(len(in_game))]
                copies = [copy.deepcopy(state), _pickled(state)] if check_copies else []
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
            snapshot = pickle.dumps(state)
            if check_copies:
                if copy.deepcopy(state) != state:
                    raise fail(f"a deep copy differs from the state after {answers} answers")
                if _pickled(state) != state:
                    raise fail(f"a pickled copy differs from the state after {answers} answers")
            agent = agent_for(agents, request.player)
            answer = agent.decide(view_for(state, request.player), request)
            if probe_invalid:
                for bad in invalid_answers(request, len(state.players), answer.value):
                    outcome = _submit(state, bad)
                    if outcome[0] != "rejected":
                        raise fail(f"the invalid answer {bad} was {outcome[0]}")
                    if state != pickle.loads(snapshot):
                        raise fail(f"the rejected answer {bad} changed the state")
            copies = [copy.deepcopy(state), _pickled(state)] if check_copies else []
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
                    if state != pickle.loads(snapshot):
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
        f"--players {len(decks)}{commander}, with the same --deck options)"
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
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status described in the module docstring."""
    parser = argparse.ArgumentParser(description="Fuzz the engine with random-agent games.")
    parser.add_argument("--games", type=int, default=200, help="number of games (default 200)")
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
    parser.add_argument(
        "--deck", type=Path, action="append", default=[], help="decklists to cycle (default: empty)"
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="card data snapshot directory")
    parser.add_argument(
        "--concessions",
        type=int,
        default=DEFAULT_CONCESSION_CHANCE,
        metavar="N",
        help="a player concedes before a decision 1 time in N (0: never)",
    )
    args = parser.parse_args(argv)
    if args.games < 1 or not args.players or min(args.players) < 2:
        parser.error("need at least one game and player counts of at least 2 (100.1)")

    fmt = "commander" if args.commander else args.format
    configs = {
        "both": [GameConfig.standard(), GameConfig.commander_game()],
        "standard": [GameConfig.standard()],
        "commander": [GameConfig.commander_game()],
    }[fmt]
    try:
        pool = _load_decks(args.deck, args.data_dir) if args.deck else [Deck(())]
    except (CardDataError, DecklistError, DeckError, OSError) as error:
        print(f"error: {error}")
        return 1

    endings: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    answers = rejected = 0
    started = time.perf_counter()
    for game in range(args.games):
        seed: int = args.seed + game
        players: int = args.players[game % len(args.players)]
        config = configs[(game // len(args.players)) % len(configs)]
        decks = [pool[(seed + seat) % len(pool)] for seat in range(players)]
        try:
            result = fuzz_game(config, decks, seed, concession_chance=args.concessions)
        except FuzzFailure as failure:
            print(f"FAILED: {failure}")
            return 1
        answers += result.answers
        rejected += result.rejected
        endings[result.gap.split(": ", 1)[0] if result.gap else "game over"] += 1
        formats["commander" if config.commander is not None else "standard"] += 1
    elapsed = time.perf_counter() - started
    print(f"{args.games} games passed: {answers} answers accepted, {rejected} rejected.")
    print("Endings: " + ", ".join(f"{name} x{count}" for name, count in sorted(endings.items())))
    print("Formats: " + ", ".join(f"{name} x{count}" for name, count in sorted(formats.items())))
    print(f"{args.games / elapsed:.1f} games per second (with every check on).")
    return 0


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
