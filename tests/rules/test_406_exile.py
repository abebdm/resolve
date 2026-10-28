"""The exile zone (406), with Swords to Plowshares ("Exile target creature. ...").

From the pinned CR:

- 406.2: "To exile an object is to put it into the exile zone from whatever zone it's currently
  in."
- 406.3: "Exiled cards are, by default, kept face up and may be examined by any player at any
  time." Face-down exile (406.3a-b) is M4.
"""

from __future__ import annotations

from resolve.engine.api import view_for
from resolve.state.ids import PlayerId
from resolve.state.spell import TargetObject
from resolve.state.turn import Phase
from resolve.state.zones import EXILE
from tests.casting_support import pass_
from tests.scenario import Scenario, names, run_script

P0, P1, P2 = PlayerId(0), PlayerId(1), PlayerId(2)


def test_406_2_406_3_an_exiled_card_is_face_up_for_every_player() -> None:
    """P0's Swords to Plowshares exiles P1's Grizzly Bears from the battlefield (406.2); every
    player, including P2 who neither cast nor owns it, sees its name in exile (406.3)."""
    scenario = Scenario(3)
    (spell,) = scenario.stack(P0, ["Swords to Plowshares"])
    (bears,) = scenario.battlefield(P1, ["Grizzly Bears"])
    scenario.targets(spell, [TargetObject(bears)])
    scenario.at(Phase.PRECOMBAT_MAIN)
    state = scenario.build()
    run_script(state, pass_(P0), pass_(P1), pass_(P2))
    assert names(state, EXILE) == ["Grizzly Bears"]
    for viewer in (P0, P1, P2):
        assert [obj.name for obj in view_for(state, viewer).exile] == ["Grizzly Bears"]
