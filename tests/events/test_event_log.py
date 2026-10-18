"""Events, the event pipeline and the event log (design.md §7)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from resolve.engine.api import view_for
from resolve.engine.loop import run
from resolve.errors import EngineError
from resolve.events.base import LogEntry, append_log
from resolve.events.game import GameEnded, LibraryShuffled, StartingPlayerChosen
from resolve.events.pipeline import ApplyEvents, detect_triggers, replacement_stage
from resolve.state.ids import PlayerId
from tests.engine_support import Counted, Mark, Marker, markers, running
from tests.game_fixtures import start

P0, P1 = PlayerId(0), PlayerId(1)


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
    entry = append_log(
        state, Marker(label="x", rules=("117.1",)), (PlayerId(1), PlayerId(0), PlayerId(1))
    )
    assert entry.visible_to == (0, 1)
    assert entry.is_visible_to(PlayerId(0))
    public = append_log(state, Marker(label="y", rules=("117.1",)), None)
    assert public.visible_to is None
    assert public.is_visible_to(PlayerId(1))
    assert public.rules == ("117.1",)


def test_an_event_is_logged_as_applied() -> None:
    """An event is proposed before its outcome is known; the log records what happened."""
    state = running(Mark("a"))
    state.pending = None
    state.tasks.append(ApplyEvents((Counted(rules=("117.1",)), Counted(rules=("117.1",)))))
    run(state)
    assert [entry.record for entry in state.event_log[1:3]] == [
        Counted(seen=1, rules=("117.1",)),
        Counted(seen=2, rules=("117.1",)),
    ]


def test_a_hidden_entry_shows_other_players_its_redacted_form() -> None:
    """design.md §9: one entry; its player sees all of it, the others its redacted form."""
    state = running(Mark("a"))
    secret = Marker(label="drew Forest", rules=("121.1",), secret_for=(P1,), public_label="drew")
    hidden = Marker(label="looked", rules=("121.1",), secret_for=(P1,))
    state.pending = None
    state.tasks.append(ApplyEvents((secret, hidden)))
    run(state)
    entry, other = state.event_log[1], state.event_log[2]
    assert entry == LogEntry(1, secret, (P1,), replace(secret, label="drew", public_label=None))
    assert other == LogEntry(2, hidden, (P1,), None)
    assert entry.shown_to(P1) == entry
    assert entry.shown_to(P0) == LogEntry(1, replace(secret, label="drew", public_label=None), None)
    assert other.shown_to(P0) is None
    assert [e.index for e in view_for(state, P0).log] == [0, 1]
    assert view_for(state, P0).log[1].record == Marker(
        label="drew", rules=("121.1",), secret_for=(P1,)
    )
    assert view_for(state, P1).log[1:] == (entry, other)


def test_a_public_entry_keeps_no_redacted_form() -> None:
    state = start(2)
    marker = Marker(label="x", rules=("117.1",))
    entry = append_log(state, marker, None, Marker(label="y", rules=("117.1",)))
    assert entry.redacted is None


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


def test_701_24a_a_shuffle_changes_only_the_named_players_library() -> None:
    state = start(3, seed=6)
    untouched = [list(p.library) for p in state.players]
    state.objects[state.players[0].library[0]].known_to = (PlayerId(0),)
    state.objects[state.players[2].library[0]].known_to = (PlayerId(1),)
    LibraryShuffled(player=PlayerId(2), rules=("701.24a",)).apply(state)
    assert state.players[0].library == untouched[0]
    assert state.players[1].library == untouched[1]
    assert state.players[2].library != untouched[2]
    assert sorted(state.players[2].library) == sorted(untouched[2])
    assert state.objects[state.players[0].library[0]].known_to == (0,)
    assert all(state.objects[obj].known_to == () for obj in state.players[2].library)
