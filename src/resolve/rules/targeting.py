"""Targeting (115, 601.2c, 608.2b, design.md §17.11).

``target_problem(state, targeter, spec, candidate)`` is the single legality check for targets:
whether ``candidate`` may be (or still is) a target of ``targeter`` for the instance of
"target" ``spec``. It is ``legality.allowed(TargetAction)``, whose permissions check, in order:

1. the kind and zone (115.2: a permanent unless the spec allows players or spells; 115.4; a
   player still in the game, 800.4a; an object still in the zone it was targeted in, 608.2b);
2. the spec's filter;

and whose prohibitions are the rules' own, a spell or ability targeting itself (115.5), and the
candidate's shroud, hexproof and protection (702.18a, 702.11b-d, 702.16b, 702.16j; a permanent's
from its characteristics, a player's from ``defaults.player_abilities``).

It is used when a spell's targets are chosen (601.2c: ``legal_targets``, and
``can_choose_targets`` for the spells priority offers), when its modes are chosen (700.2a: a mode
without enough legal targets can't be, ``legal_modes`` and ``mode_choices``), when it resolves
(608.2b), and from M4 and M5 by abilities and by changing targets (115.7). Everything calls it
through the module (``targeting.target_problem``), so a test that replaces it is obeyed
everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from resolve.cards.primitives.spells import SpellAbility
from resolve.cards.primitives.targets import TargetSpec
from resolve.effects.characteristics import variant_characteristics
from resolve.errors import EngineError
from resolve.rules import legality, targeting
from resolve.rules.legality import Targeter, Verdict
from resolve.state.game import players_in_game
from resolve.state.ids import ObjectId, PlayerId
from resolve.state.spell import CastVariant, Target, TargetObject, TargetPlayer

if TYPE_CHECKING:
    from resolve.state.game import GameState


def target_problem(
    state: GameState, targeter: Targeter, spec: TargetSpec, candidate: Target
) -> Verdict | None:
    """Why ``candidate`` can't be a target of ``targeter`` for ``spec`` now, or ``None`` if it
    can (115, 601.2c, 608.2b)."""
    action = legality.TargetAction(targeter.controller, targeter, spec, candidate)
    verdict = legality.allowed(state, action)
    return None if verdict.allowed else verdict


def legal_targets(state: GameState, targeter: Targeter, spec: TargetSpec) -> tuple[Target, ...]:
    """Every object and player ``targeter`` may choose for ``spec`` now (601.2c): permanents in
    battlefield order, then spells from the top of the stack down, then players in turn order."""
    candidates: list[Target] = []
    if spec.objects is not None:
        candidates += [TargetObject(obj) for obj in state.battlefield]
    if spec.spells is not None:
        candidates += [TargetObject(obj) for obj in reversed(state.stack)]
    if spec.players is not None:
        candidates += [TargetPlayer(player) for player in players_in_game(state)]
    return tuple(
        candidate
        for candidate in candidates
        if targeting.target_problem(state, targeter, spec, candidate) is None
    )


def legal_modes(state: GameState, targeter: Targeter, ability: SpellAbility) -> tuple[int, ...]:
    """The modes of the modal ``ability`` that may be chosen now (700.2a), by index in printed
    order: those whose every instance of "target" has at least its minimum of legal targets
    (601.2c). Each instance is judged alone (115.3, 700.2d: a repeated mode may choose the same
    target again), so one mode's legality doesn't depend on the others chosen."""
    return tuple(
        index
        for index, mode in enumerate(ability.modes)
        if all(
            len(targeting.legal_targets(state, targeter, spec)) >= spec.minimum
            for spec in mode.targets
        )
    )


def mode_choices(
    state: GameState, targeter: Targeter, ability: SpellAbility
) -> tuple[tuple[int, ...], ...]:
    """Every choice of modes the controller of the modal ``ability`` may make now (601.2b,
    700.2a, 700.2d): the combinations of its legal modes its ``ModeChoice`` allows."""
    if ability.choose is None:
        raise EngineError("a spell that isn't modal has no modes to choose")
    return ability.choose.combinations(targeting.legal_modes(state, targeter, ability))


def can_choose_targets(
    state: GameState, player: PlayerId, card: ObjectId, variant: CastVariant
) -> bool:
    """Whether ``player`` could choose legal targets for every instance of "target" the card
    ``card`` requires if cast as ``variant`` now (601.2c): at least each instance's minimum.
    Different instances may choose the same object (115.3), so each is judged alone. A modal
    spell needs some legal choice of modes (700.2a, 601.2b); the targets of the modes not chosen
    don't count (700.2c)."""
    characteristics = variant_characteristics(state, card, variant)
    ability = characteristics.spell_ability
    if ability is None:
        return True
    targeter = Targeter(player, card, characteristics)
    if ability.choose is not None:
        return bool(targeting.mode_choices(state, targeter, ability))
    return all(
        len(legal_targets(state, targeter, spec)) >= spec.minimum
        for spec in ability.modes[0].targets
    )
