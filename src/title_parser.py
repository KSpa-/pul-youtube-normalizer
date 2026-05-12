"""Parse messy current YouTube titles to extract the two team names and
optionally the game date if one is embedded in the title.

Week and home/away always come from the stats hub.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Optional


_TITLE_DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")


def parse_date_from_title(title: str) -> Optional[datetime.date]:
    """Extract a US-format date (M/D/YY or M/D/YYYY) from a title.

    Returns None if no recognizable date is present or if the components
    don't form a valid calendar date. Two-digit years are interpreted as
    20YY (so "6/10/23" -> 2023-06-10). Only the first match is returned.
    """
    m = _TITLE_DATE_PATTERN.search(title)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class TeamIndex:
    """Lowercase name/alias -> canonical full team name, plus sorted name list."""
    canonical_by_lower: dict[str, str]
    # Names sorted longest-first so longer aliases match before shorter substrings
    # (e.g., "Atlanta Soul" matches before bare "Soul").
    names_longest_first: list[str]


def load_team_index(raw: dict) -> TeamIndex:
    """Build a TeamIndex from raw team_abbreviations.json data.

    The input shape is `{full_name: {"short": str, "aliases": list[str]}}`.
    Each full name and each alias is registered (lowercased) as a key pointing
    to the canonical full name. The resulting `names_longest_first` list lets
    callers prefer longer matches over shorter substrings.
    """
    canonical_by_lower: dict[str, str] = {}
    for full_name, meta in raw.items():
        canonical_by_lower[full_name.lower()] = full_name
        for alias in meta.get("aliases", []):
            canonical_by_lower[alias.lower()] = full_name
    names = sorted(canonical_by_lower.keys(), key=len, reverse=True)
    return TeamIndex(canonical_by_lower=canonical_by_lower, names_longest_first=names)


def parse_teams(title: str, idx: TeamIndex) -> Optional[tuple[str, str]]:
    """Return (first_team, second_team) by order of appearance in the title.

    Returns None if fewer than 2 distinct teams found.
    """
    haystack = title.lower()
    # Track each (start_index, canonical_name); claim characters so we don't match
    # overlapping aliases (e.g., "Indy Red" shouldn't also match a separate "Red").
    claimed = [False] * len(haystack)
    found: list[tuple[int, str]] = []

    for name in idx.names_longest_first:
        # Word-boundary-ish match to avoid partials like "ATL" matching inside "atlas"
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        for m in re.finditer(pattern, haystack):
            start, end = m.span()
            if any(claimed[start:end]):
                continue
            for i in range(start, end):
                claimed[i] = True
            canonical = idx.canonical_by_lower[name]
            # Skip duplicate canonical (e.g., "Indy Red" and "Indianapolis Red" both matched)
            if any(canonical == c for _, c in found):
                continue
            found.append((start, canonical))

    found.sort(key=lambda pair: pair[0])
    if len(found) < 2:
        return None
    return (found[0][1], found[1][1])
