"""Events, the event pipeline and the event log (design.md §7)."""

from __future__ import annotations

import pytest

from resolve.engine.loop import run
from resolve.errors import EngineError
from resolve.events.base import LogEntry, append_log
from resolve.events.game import GameEnded, LibraryShuffled, StartingPlayerChosen
from resolve.events.pipeline import ApplyEvents, detect_triggers, replacement_stage
from resolve.state.ids import PlayerId
from tests.engine_support import Mark, Marker, markers, running
from tests.game_fixtures import start


def test_simultaneous_events_are_applied_and_logged_in_order() -> None:
    state = running(Mark("a"))
    events = (
        Marker(label="first", rules=("117.1",)),
        Marker(label="second", rules=("117.1",), secret_for=(PlayerId(1),)),
    )
    state.pending = None
    state.tasks.append(ApplyEvents(events))
    run(state)
    assert markers(state) == ["a", "first", "second"]
    assert [entry.index for entry in state.event_log] == [0, 1, 2]
    assert state.event_log[2] == LogEntry(2, events[1], (PlayerId(1),))


def test_log_entries_record_visibility_sorted_and_without_repeats() -> None:
    state = start(2)
    entry = append_log(state, Marker(label="x", rules=("117.1",)), (PlayerId(1), PlayerId(0), PlayerId(1)))
    assert entry.visible_to == (0, 1)
    assert entry.is_visible_to(PlayerId(0))
    public = append_log(state, Marker(label="y", rules=("117.1",)), None)
    assert public.visible_to is None
    assert public.is_visible_to(PlayerId(1))
    assert public.rules == ("117.1",)


@pytest.mark.parametrize("rules", [("103",), ("103.1",), ("701.24a",), ("103.3", "701.24a")])
def test_events_cite_sections_rules_or_subrules(rules: tuple[str, ...]) -> None:
    assert Marker(label="ok", rules=rules).rules == rules


@pytest.mark.parametrize("rules", [(), ("abc",), ("103.1", ""), ("1.2",), ("103.1A",)])
def test_events_must_cite_valid_rules(rules: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="CR citation"):
        Marker(label="bad", rules=rules)


def test_apply_events_needs_at_least_one_event() -> None:
    with pytest.raises(EngineError, match="at least one event"):
        ApplyEvents(())


def test_the_replacement_and_trigger_hooks_change_nothing_yet() -> None:
    """614-616 (M6) and 603.2 (M4): nothing can create such effects or abilities yet."""
    state = start(2)
    events = (Marker(label="x", rules=("117.1",)),)
    assert replacement_stage(state, events) is events
    detect_triggers(state, events)
    assert state.event_log == []


def test_701_24a_after_a_shuffle_nobody_knows_where_a_card_is() -> None:
    state = start(2)
    library = state.players[0].library
    state.objects[library[-1]].known_to = (PlayerId(0),)  # as if seen by scry
    LibraryShuffled(player=PlayerId(0), rules=("701.24a",)).apply(state)
    assert all(state.objects[obj].known_to == () for obj in library)


def test_the_starting_player_can_only_be_chosen_once() -> None:
    state = start(2)
    event = StartingPlayerChosen(chooser=PlayerId(0), starting_player=PlayerId(1), rules=("103.1",))
    event.apply(state)
    with pytest.raises(EngineError, match="already"):
        event.apply(state)


def test_the_starting_player_must_be_a_player() -> None:
    state = start(2)
    with pytest.raises(EngineError, match="no player 5"):
        StartingPlayerChosen(
            chooser=PlayerId(0), starting_player=PlayerId(5), rules=("103.1",)
        ).apply(state)


def test_104_4a_a_game_with_no_winners_is_a_draw() -> None:
    state = start(3)
    GameEnded(winners=(), rules=("104.4a",)).apply(state)
    assert state.result is not None
    assert state.result.is_draw


def test_104_1_the_game_ends_once() -> None:
    state = start(3)
    GameEnded(winners=(PlayerId(2), PlayerId(0), PlayerId(2)), rules=("104.1",)).apply(state)
    assert state.result is not None
    assert state.result.winners == (0, 2)
    assert not state.result.is_draw
    with pytest.raises(EngineError, match="already over"):
        GameEnded(winners=(), rules=("104.1",)).apply(state)


def test_winners_must_be_players() -> None:
    with pytest.raises(EngineError, match="no player 3"):
        GameEnded(winners=(PlayerId(3),), rules=("104.1",)).apply(start(3))
