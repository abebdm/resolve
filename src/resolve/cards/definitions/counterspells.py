"""Instants that counter spells: Cryptic Command (Cancel is a keyword example card,
``keyword_examples``)."""

from __future__ import annotations

from resolve.cards.primitives.effects import CounterSpell, DrawCards, ReturnToHand, TapAll
from resolve.cards.primitives.refs import EachCreature, EachOpponent, TargetRef
from resolve.cards.primitives.spells import Mode, ModeChoice, SpellAbility
from resolve.cards.primitives.targets import ObjectFilter, SpellFilter, TargetSpec
from resolve.cards.registry import CardDefinition

_IT = TargetRef(0)

# Choose two —
# • Counter target spell.
# • Return target permanent to its owner's hand.
# • Tap all creatures your opponents control.
# • Draw a card.
CRYPTIC_COMMAND = CardDefinition(
    "Cryptic Command",
    spell=SpellAbility(
        (
            Mode((TargetSpec(spells=SpellFilter()),), (CounterSpell((_IT,)),)),
            Mode((TargetSpec(objects=ObjectFilter()),), (ReturnToHand((_IT,)),)),
            Mode((), (TapAll(EachCreature(controlled_by=EachOpponent())),)),
            Mode((), (DrawCards(),)),
        ),
        ModeChoice(2, 2),
    ),
)

DEFINITIONS = (CRYPTIC_COMMAND,)
