"""The payment search behind 601.2h (``resolve.engine.payment``), tested on its own.

From the pinned CR: 107.4a, each colored symbol is paid with one mana of its color; 107.4c, {C}
with one colorless mana; 107.4b, generic mana with mana of any type. 601.2h: partial payments
aren't allowed, so a payment spends exactly the cost's total. {X} (107.3a), hybrid and Phyrexian
symbols (107.4e-f) and {S} (107.4h) are paid otherwise, and are gaps.
"""

from __future__ import annotations

import pytest

from resolve.data.mana_cost import parse_mana_cost
from resolve.engine.payment import ManaNeed, mana_classes, mana_need, payments
from resolve.errors import NotImplementedRule
from resolve.state.ids import ObjectId
from resolve.state.mana import Mana, ManaType

W, U, R, G, C = (ManaType.WHITE, ManaType.BLUE, ManaType.RED, ManaType.GREEN, ManaType.COLORLESS)
A, B = ObjectId(1), ObjectId(2)


def test_107_4_what_a_cost_needs() -> None:
    assert mana_need(parse_mana_cost("{3}{R}")) == ManaNeed(((R, 1),), 4)
    assert mana_need(parse_mana_cost("{C}{C}{G}")) == ManaNeed(((C, 2), (G, 1)), 3)
    assert mana_need(parse_mana_cost("{0}")) == ManaNeed((), 0)


@pytest.mark.parametrize(
    ("cost", "rule"),
    [("{X}{R}", "107.3a"), ("{S}", "107.4h"), ("{W/U}", "107.4e"), ("{G/P}", "107.4e")],
)
def test_symbols_paid_otherwise_are_gaps(cost: str, rule: str) -> None:
    with pytest.raises(NotImplementedRule) as gap:
        mana_need(parse_mana_cost(cost))
    assert gap.value.rule == rule


def test_classes_are_equal_units_in_order_of_first_appearance() -> None:
    pool = [Mana(G, A), Mana(W), Mana(G, A), Mana(G, B)]
    assert mana_classes(pool) == ((Mana(G, A), 2), (Mana(W), 1), (Mana(G, B), 1))


def test_107_4a_c_a_payment_needs_each_colored_and_colorless_symbol_paid_by_its_type() -> None:
    need = mana_need(parse_mana_cost("{1}{G}"))
    assert need.paid_by([(Mana(G), 1), (Mana(W), 1)])
    assert need.paid_by([(Mana(G), 2)])
    assert not need.paid_by([(Mana(W), 2)])  # 107.4a
    assert not need.paid_by([(Mana(G), 1)])  # 601.2h: no partial payment
    assert not need.paid_by([(Mana(G), 3)])  # exactly the total
    assert not mana_need(parse_mana_cost("{C}")).paid_by([(Mana(G), 1)])  # 107.4c


def test_payments_lists_the_ways_up_to_the_limit() -> None:
    classes = ((Mana(G), 2), (Mana(W), 2))
    need = mana_need(parse_mana_cost("{1}{G}"))
    assert payments(classes, need, limit=5) == [(1, 1), (2, 0)]
    assert len(payments(classes, need, limit=1)) == 1
    assert payments(((Mana(W), 4),), need, limit=5) == []  # no green: nothing pays
    assert payments((), mana_need(parse_mana_cost("{0}")), limit=5) == [()]


def test_payments_with_many_classes_stop_at_the_limit() -> None:
    """Twenty single units of different sources and a cost of {10}: thousands of ways; the
    search stops at the limit (601.2h only needs to know whether there are 0, 1 or more)."""
    classes = tuple((Mana(G, ObjectId(i)), 1) for i in range(1, 21))
    assert len(payments(classes, mana_need(parse_mana_cost("{10}")), limit=2)) == 2
