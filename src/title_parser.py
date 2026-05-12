"""Parse messy current YouTube titles to extract the two team names.

Does NOT extract date, week, or home/away — those come from the stats hub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TeamIndex:
    """Lowercase name/alias -> canonical full team name, plus sorted name list."""
    canonical_by_lower: dict[str, str]
    # Names sorted longest-first so longer aliases match before shorter substrings
    # (e.g., "Atlanta Soul" matches before bare "Soul").
    names_longest_first: list[str]


def load_team_index(raw: dict) -> TeamIndex:
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
