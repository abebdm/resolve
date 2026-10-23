"""Targeting (115, 601.2c, 608.2b, design.md §17.11).

``target_problem(state, targeter, spec, candidate)`` is the single legality check for targets:
whether ``candidate`` may be (or still is) a target of ``targeter`` for the instance of
"target" ``spec``. It is ``legality.allowed(TargetAction)``, whose permissions check, in order:

1. the kind and zone (115.2: a permanent unless the spec allows players or spells; 115.4; a
   player still in the game, 800.4a; an object still in the zone it was targeted in, 608.2b);
2. the spec's filter;
3. that a spell or ability isn't targeting itself (115.5);

and whose prohibitions, from M2.8, are the candidate's shroud, hexproof and protection
(702.18a, 702.11b-d, 702.16b).

It is used when a spell's targets are chosen (601.2c: ``legal_targets``, and
``can_choose_targets`` for the spells priority offers), when it resolves (608.2b), and from M4
and M5 by abilities and by changing targets (115.7). Everything calls it through the module
(``targeting.target_problem``), so a test that replaces it is obeyed everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.cards.primitives.targets import TargetSpec
from resolve.errors import NotImplementedRule
from resolve.rules import legality
from resolve.rules.legality import Targeter, Verdict
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import CastVariant, Target

if TYPE_CHECKING:
    from resolve.state.game import GameState


def target_problem(
    state: GameState, targeter: Targeter, spec: TargetSpec, candidate: Target
) -> Verdict | None:
    """Why ``candidate`` can't be a target of ``targeter`` for ``spec`` now, or ``None`` if it
    can (115, 601.2c, 608.2b)."""
    verdict = legality.allowed(state, legality.TargetAction(targeter.controller, targeter, spec, candidate))
    return None if verdict.allowed else verdict


def legal_targets(state: GameState, targeter: Targeter, spec: TargetSpec) -> tuple[Target, ...]:
    """Every object and player ``targeter`` may choose for ``spec`` now (601.2c)."""
    raise NotImplementedRule("601.2c: listing the legal targets (M2.6, stub)")


def can_choose_targets(
    state: GameState, player: PlayerId, card: ObjectId, variant: CastVariant
) -> bool:
    """Whether ``player`` could choose legal targets for every instance of "target" the card
    ``card`` requires if cast as ``variant`` now (601.2c)."""
    raise NotImplementedRule("601.2c: whether a spell has legal targets (M2.6, stub)")
