"""Keyword abilities and keyword actions (CR 701-702), built from primitives.

- ``evergreen``: flash, haste, hexproof, shroud, indestructible, protection (702.8, 702.10,
  702.11, 702.12, 702.16, 702.18), with ``has_keyword`` and ``keywords``;
- ``combat``: the evasion keywords flying, intimidate, landwalk, fear and menace, and reach
  (702.9, 702.13, 702.14, 702.36, 702.111, 702.17);
- ``qualities``: what protection and "hexproof from" are from (702.16a), and landwalk's land
  type (702.14a).
"""

from resolve.cards.keywords.combat import Fear, Flying, Intimidate, Landwalk, Menace, Reach
from resolve.cards.keywords.evergreen import (
    Defender,
    Flash,
    Haste,
    Hexproof,
    Indestructible,
    Protection,
    Shroud,
    Vigilance,
    has_keyword,
    keywords,
    protection_from_each_color,
)
from resolve.cards.keywords.qualities import (
    CardTypeQuality,
    ColorQuality,
    Everything,
    LandTypeQuality,
    MonocoloredQuality,
    MulticoloredQuality,
    PlayerQuality,
    Quality,
    SubtypeQuality,
    each_color,
)

__all__ = [
    "CardTypeQuality",
    "ColorQuality",
    "Defender",
    "Everything",
    "Fear",
    "Flash",
    "Flying",
    "Haste",
    "Hexproof",
    "Indestructible",
    "Intimidate",
    "LandTypeQuality",
    "Landwalk",
    "Menace",
    "MonocoloredQuality",
    "MulticoloredQuality",
    "PlayerQuality",
    "Protection",
    "Quality",
    "Reach",
    "Shroud",
    "SubtypeQuality",
    "Vigilance",
    "each_color",
    "has_keyword",
    "keywords",
    "protection_from_each_color",
]
