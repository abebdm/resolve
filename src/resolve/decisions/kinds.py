"""Decision kinds: *what* a player is being asked (design.md §6).

The kind tells a UI or an AI what the question means; the answer space (``spaces.py``) says what
shape of answer is allowed. The two are independent: for example, ordering triggers and ordering
cards put on the bottom of a library both use ``ChooseOrder``.

This enum is the vocabulary listed in design.md §6. A kind only becomes something the engine asks
once the task that asks it exists; in M0 that is ``CHOOSE_STARTING_PLAYER`` alone.
"""

from __future__ import annotations

from enum import Enum, unique


@unique
class DecisionKind(Enum):
    """The kinds of decisions players make, each with the rule that asks for it."""

    CHOOSE_STARTING_PLAYER = "choose_starting_player"  # 103.1
    MULLIGAN = "mulligan"  # 103.5
    PRIORITY_ACTION = "priority_action"  # 117.1
    CHOOSE_MODES = "choose_modes"  # 700.2, 601.2b
    CHOOSE_X = "choose_x"  # 107.3a
    CHOOSE_TARGETS = "choose_targets"  # 601.2c
    DIVIDE = "divide"  # 601.2d
    PAY_COSTS = "pay_costs"  # 601.2h
    DECLARE_ATTACKERS = "declare_attackers"  # 508.1
    DECLARE_BLOCKERS = "declare_blockers"  # 509.1
    ASSIGN_COMBAT_DAMAGE = "assign_combat_damage"  # 510.1
    ORDER_TRIGGERS = "order_triggers"  # 603.3b
    ORDER_REPLACEMENTS = "order_replacements"  # 616.1
    CHOOSE_CARD_NAME = "choose_card_name"  # 201.4
    MAY = "may"  # 603.5 and other optional instructions
