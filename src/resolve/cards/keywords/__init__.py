"""Keyword abilities and keyword actions (CR 701-702), built from primitives.

- ``evergreen``: flash, hexproof, shroud, indestructible, protection (702.8, 702.11, 702.12,
  702.16, 702.18), with ``has_keyword`` and ``keywords``;
- ``qualities``: what protection and "hexproof from" are from (702.16a).
"""

from resolve.cards.keywords.evergreen import (
    Flash,
    Hexproof,
    Indestructible,
    Protection,
    Shroud,
    has_keyword,
    keywords,
    protection_from_each_color,
)
from resolve.cards.keywords.qualities import (
    CardTypeQuality,
    ColorQuality,
    Everything,
    MonocoloredQuality,
    MulticoloredQuality,
    Quality,
    SubtypeQuality,
    each_color,
)

__all__ = [
    "CardTypeQuality",
    "ColorQuality",
    "Everything",
    "Flash",
    "Hexproof",
    "Indestructible",
    "MonocoloredQuality",
    "MulticoloredQuality",
    "Protection",
    "Quality",
    "Shroud",
    "SubtypeQuality",
    "each_color",
    "has_keyword",
    "keywords",
    "protection_from_each_color",
]
