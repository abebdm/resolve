"""Pytest options for the test suite.

``--thorough``: the long preset of the tests whose length is a trade-off (CLAUDE.md, "Quick runs
for agents, thorough runs for the user's milestone checks"; listed in docs/verification.md). Only
``tests/agents/test_autopay_brute_force.py`` has one so far.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--thorough",
        action="store_true",
        default=False,
        help="run the long presets of the tests that have one (docs/verification.md)",
    )


@pytest.fixture
def thorough(request: pytest.FixtureRequest) -> bool:
    """Whether ``--thorough`` was given."""
    return bool(request.config.getoption("--thorough"))
