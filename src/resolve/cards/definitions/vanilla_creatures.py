"""Vanilla creatures: creature cards with no rules text (Grizzly Bears, Savannah Lions, Hill
Giant). Their characteristics, power and toughness included, come from the card data; their
definitions have no abilities."""

from __future__ import annotations

from resolve.cards.registry import CardDefinition

GRIZZLY_BEARS = CardDefinition("Grizzly Bears")
SAVANNAH_LIONS = CardDefinition("Savannah Lions")
HILL_GIANT = CardDefinition("Hill Giant")

DEFINITIONS = (GRIZZLY_BEARS, SAVANNAH_LIONS, HILL_GIANT)
