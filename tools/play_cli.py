"""Play a game in the terminal: humans (hot-seat) and random agents.

Usage::

    uv run python tools/play_cli.py                          # two players, empty decks
    uv run python tools/play_cli.py --players 4 --commander  # a four-player Commander game
    uv run python tools/play_cli.py --random 1 2             # seats 1 and 2 play randomly
    uv run python tools/play_cli.py --deck decks/a.txt --deck decks/b.txt

Each human seat sees only its own view (design.md §9). At the end the final view is shown only
if a single seat is human (or, when every seat is random, player 0's). A ``--random`` seat ``i``
plays as ``RandomAgent(agent_seed + i)``. Answers are typed as described in
``resolve.agents.text`` (``help`` at the prompt). With ``--deck``, one decklist per player, the
cards come from the snapshot in ``data/`` and every card must be implemented; decks are refused,
never approximated. Without ``--deck`` every player gets an empty deck, since no card is
implemented yet.

Exit status: 0 the game ended; 1 the game couldn't start (bad deck, missing card data);
2 bad arguments; 3 the game reached a rule the engine doesn't implement yet (every M0 game stops
at 103.5); 4 a person quit.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from resolve.agents.base import Agent
from resolve.agents.driver import play
from resolve.agents.random_agent import RandomAgent
from resolve.agents.text import QuitGame, TextAgent, render_view
from resolve.cards.registry import default_registry
from resolve.data.cards import CardDataError, load_card_database
from resolve.data.decklist import DecklistError, load_decklist
from resolve.engine.api import new_game, view_for
from resolve.engine.deck import Deck, build_deck
from resolve.errors import DeckError, InvalidAnswer, NotImplementedRule
from resolve.state.config import GameConfig
from resolve.state.game import GameState
from resolve.state.ids import PlayerId

EXIT_OVER = 0
EXIT_CANT_START = 1
EXIT_GAP = 3
EXIT_QUIT = 4


def load_decks(paths: Sequence[Path], data_dir: Path | None) -> list[Deck]:
    """Build one deck per decklist from the card data snapshot and the registry."""
    database = load_card_database(data_dir)
    registry = default_registry()
    return [build_deck(load_decklist(path), database, registry) for path in paths]


def play_game(
    state: GameState, agents: Sequence[Agent], output: TextIO, *, viewer: PlayerId | None
) -> int:
    """Drive ``state`` with ``agents`` and report how it ended; returns the exit status.

    At the end, ``viewer``'s view is printed: the one human at the terminal. With several humans
    (hot-seat) ``viewer`` is ``None`` and no hand is shown, only how the game ended.
    """

    def final_view() -> None:
        if viewer is not None:
            print(render_view(view_for(state, viewer)), file=output)
        elif state.result is not None:
            winners = ", ".join(f"player {p}" for p in state.result.winners)
            print(
                f"Game over: {'a draw' if state.result.is_draw else 'won by ' + winners}.",
                file=output,
            )

    def rejected(error: InvalidAnswer) -> None:
        print(f"The engine rejected that answer: {error}", file=output, flush=True)

    try:
        play(state, agents, on_invalid=rejected)
    except NotImplementedRule as gap:
        final_view()
        print(f"Stopped: the engine doesn't implement {gap} yet.", file=output)
        return EXIT_GAP
    except QuitGame:
        print("Game abandoned.", file=output)
        return EXIT_QUIT
    final_view()
    return EXIT_OVER


def main(
    argv: Sequence[str] | None = None, *, input: TextIO | None = None, output: TextIO | None = None
) -> int:
    """Run the command line; returns the exit status described in the module docstring."""
    out: TextIO = sys.stdout if output is None else output
    parser = argparse.ArgumentParser(description="Play Resolve in the terminal.")
    parser.add_argument("--players", type=int, default=None, help="number of players (default 2)")
    parser.add_argument("--commander", action="store_true", help="use the Commander rules (903)")
    parser.add_argument("--seed", type=int, default=1, help="the game's seed, 0 to 2**64 - 1")
    parser.add_argument(
        "--deck", type=Path, action="append", default=[], help="a decklist, one per player"
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="card data snapshot directory")
    parser.add_argument(
        "--random", type=int, nargs="*", default=[], metavar="SEAT", help="seats played randomly"
    )
    parser.add_argument("--agent-seed", type=int, default=0, help="seed for the random agents")
    args = parser.parse_args(argv)

    decks_given: list[Path] = args.deck
    players: int = args.players if args.players is not None else (len(decks_given) or 2)
    if decks_given and len(decks_given) != players:
        parser.error(f"give one --deck per player ({players} players, {len(decks_given)} decks)")
    if players < 2:
        parser.error("a game needs at least two players (100.1)")
    seats: list[int] = args.random
    if any(not 0 <= seat < players for seat in seats):
        parser.error(f"--random seats must be between 0 and {players - 1}")
    if not 0 <= args.agent_seed <= 2**64 - players:
        parser.error("--agent-seed must be between 0 and 2**64 minus the number of players")
    config = GameConfig.commander_game() if args.commander else GameConfig.standard()

    try:
        if decks_given:
            decks = load_decks(decks_given, args.data_dir)
        else:
            print("No --deck given: every player gets an empty deck.", file=out)
            decks = [Deck(()) for _ in range(players)]
        state = new_game(config, decks, args.seed)
    except (CardDataError, DecklistError, DeckError, OSError) as error:
        print(f"error: {error}", file=out)
        return EXIT_CANT_START
    except ValueError as error:  # a seed out of range
        parser.error(str(error))
    except NotImplementedRule as gap:
        print(f"Stopped: the engine doesn't implement {gap} yet.", file=out)
        return EXIT_GAP

    human = TextAgent(input, out)
    agents: list[Agent] = [
        RandomAgent(args.agent_seed + seat) if seat in seats else human for seat in range(players)
    ]
    humans = [PlayerId(seat) for seat in range(players) if seat not in seats]
    # The one human's view; player 0's when only random agents play; no one's in hot-seat play.
    viewer = humans[0] if len(humans) == 1 else (PlayerId(0) if not humans else None)
    return play_game(state, agents, out, viewer=viewer)


if __name__ == "__main__":
    # Redirected output would use the locale's code page, cp1252 on Windows, which can't encode
    # every card or path name; write UTF-8 everywhere (CLAUDE.md, Platform).
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
