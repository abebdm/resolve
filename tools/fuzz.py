"""The fuzz harness: random-agent games, checked after every decision (design.md §14).

Usage::

    uv run python tools/fuzz.py                       # 200 games, 2 to 6 players, both formats
    uv run python tools/fuzz.py --games 1000 --seed 5000
    uv run python tools/fuzz.py --deck a.txt --deck b.txt  # decks from the snapshot, cycled

Each game is played by ``RandomAgent``s. Before every answer the harness checks:

- the state's bookkeeping invariants and that it is pure data (``resolve.state.invariants``);
- every player's view: deeply immutable, holding the request only for the deciding player, and
  naming no card its viewer may not know (400.2, 401.3, 402.3);
- that the state survives ``copy.deepcopy`` and ``pickle`` unchanged;
- that answers outside the answer space, for another request or from another player are
  rejected and change nothing (design.md §6);

and then submits the agent's answer to the state, to a deep copy and to a pickled copy, which
must all end the same way and in equal states: a state copied mid-task resumes exactly as the
original (design.md §5). A random answer the asking task rejects must change nothing; the agent
answers again. At the end, the game is replayed from its config, decks, seed and recorded
answers and must reproduce the identical state (design.md §12).

A game ends when it is over or when it reaches a ``NotImplementedRule`` for an allowed rule.
Until M1 every game stops at ``NotImplementedRule("103.5: ...")``, which is the end of an M0
game (roadmap). Any other exception, a disallowed gap, or a failed check raises ``FuzzFailure``
naming the seed. The command line prints games per second as a rough benchmark.

Exit status: 0 every game passed; 1 a game failed, or the decks couldn't be built.
"""

from __future__ import annotations

import argparse
import copy
import pickle
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from resolve.agents.driver import MAX_ATTEMPTS, agent_for, play
from resolve.agents.random_agent import RandomAgent
from resolve.agents.scripted import ScriptedAgent
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
from resolve.engine.deck import Deck, build_deck
from resolve.engine.view import is_known_to
from resolve.errors import DeckError, InvalidAnswer, NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId
from resolve.state.invariants import invariant_violations, mutable_parts, state_impurities

# Gaps that end a fuzz game normally. Until M1 every game stops at 103.5 (roadmap M0).
ALLOWED_GAPS: tuple[str, ...] = ("103.5",)
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


def _pickled(state: GameState) -> GameState:
    restored: GameState = pickle.loads(pickle.dumps(state))
    return restored


def state_problems(state: GameState) -> list[str]:
    """Everything wrong with ``state`` and the views built from it."""
    problems = invariant_violations(state) + state_impurities(state)
    request = state.pending
    for player in state.players:
        view = view_for(state, player.id)
        problems += mutable_parts(view, f"view_for({player.id})")
        expected = request if request is not None and request.player == player.id else None
        if view.request != expected:
            problems.append(f"player {player.id}'s view holds the wrong request")
        if any(
            summary.library_size != len(state.player(summary.id).library)
            for summary in view.players
        ):
            problems.append(f"player {player.id}'s view miscounts a library")
        for summary in view.players:
            for shown in summary.hand + summary.graveyard:
                obj = state.objects[shown.id]
                if (shown.name is not None) != is_known_to(obj, player.id):
                    problems.append(f"player {player.id}'s view of object {shown.id} is wrong")
    return problems


def invalid_answers(request: DecisionRequest, players: int) -> list[DecisionAnswer]:
    """Answers that must be rejected: another request, another player, outside the space."""

    def answer(value: AnswerValue) -> DecisionAnswer:
        return DecisionAnswer(request.id, request.player, value)

    some_value: AnswerValue = Number(0) if not isinstance(request.space, ChooseNumber) else Pick(0)
    wrong: list[DecisionAnswer] = [
        DecisionAnswer(request.id + 1, request.player, some_value),
        DecisionAnswer(request.id - 1, request.player, some_value),
        answer(some_value),  # a value of the wrong type for the space
    ]
    if players > 1:
        other = PlayerId((request.player + 1) % players)
        wrong.append(DecisionAnswer(request.id, other, some_value))
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
    agents: Sequence[RandomAgent],
    *,
    describe: str,
    allowed_gaps: Sequence[str] = ALLOWED_GAPS,
    max_answers: int = MAX_ANSWERS,
    check_copies: bool = True,
    probe_invalid: bool = True,
) -> FuzzResult:
    """Play the game ``make_state()`` starts with ``agents`` (one per seat), checking it.

    ``make_state`` is called again for the replay, and must start the same game each time.
    ``describe`` names the game in failure messages (for example, how to reproduce it).
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
    try:
        while gap is None:
            check(state, f"after {answers} answers")
            request = pending_decision(state)
            if request is None:
                break
            if answers >= max_answers:
                raise fail(f"the game didn't end within {max_answers} answers")
            snapshot = pickle.dumps(state)
            if check_copies:
                if copy.deepcopy(state) != state:
                    raise fail(f"a deep copy differs from the state after {answers} answers")
                if _pickled(state) != state:
                    raise fail(f"a pickled copy differs from the state after {answers} answers")
            if probe_invalid:
                for bad in invalid_answers(request, len(state.players)):
                    outcome = _submit(state, bad)
                    if outcome[0] != "rejected":
                        raise fail(f"the invalid answer {bad} was {outcome[0]}")
                    if state != pickle.loads(snapshot):
                        raise fail(f"the rejected answer {bad} changed the state")
            agent = agent_for(agents, request.player)
            answer = agent.decide(view_for(state, request.player), request)
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
    """Replaying the recorded answers from the start must reproduce ``state`` (design.md §12)."""
    again = make_state()
    script = ScriptedAgent.from_log(state.event_log)
    replay_gap: str | None = None
    try:
        play(again, script)
    except NotImplementedRule as error:
        replay_gap = str(error)
    except Exception as error:
        raise fail(f"the replay failed: {type(error).__name__}: {error}") from error
    if replay_gap != gap or script.remaining:
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
    answers = rejected = 0
    started = time.perf_counter()
    for game in range(args.games):
        seed = args.seed + game
        players: int = args.players[game % len(args.players)]
        config = configs[(game // len(args.players)) % len(configs)]
        decks = [pool[(game + seat) % len(pool)] for seat in range(players)]
        try:
            result = fuzz_game(config, decks, seed)
        except FuzzFailure as failure:
            print(f"FAILED: {failure}")
            return 1
        answers += result.answers
        rejected += result.rejected
        endings[result.gap.split(": ", 1)[0] if result.gap else "game over"] += 1
    elapsed = time.perf_counter() - started
    print(f"{args.games} games passed: {answers} answers accepted, {rejected} rejected.")
    print("Endings: " + ", ".join(f"{name} x{count}" for name, count in sorted(endings.items())))
    print(f"{args.games / elapsed:.1f} games per second (with every check on).")
    return 0


def _load_decks(paths: Sequence[Path], data_dir: Path | None) -> list[Deck]:
    database = load_card_database(data_dir)
    registry = default_registry()
    return [build_deck(load_decklist(path), database, registry) for path in paths]


if __name__ == "__main__":
    sys.exit(main())
