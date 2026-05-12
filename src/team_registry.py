"""Canonical PUL team registry loaded from data/teams_info.json.

This module is the single source of truth for team names and locations.
Both the scraper (to map hub-team-strings to canonical names) and the
normalizer (to render descriptions) consume from here.
"""
from __future__ import annotations

import json
from pathlib import Path


TEAMS_INFO_PATH = Path("data/teams_info.json")


def load_teams(path: Path = TEAMS_INFO_PATH) -> dict[str, dict]:
    """Return mapping of canonical team name -> team info dict."""
    return json.loads(path.read_text(encoding="utf-8"))


# Eagerly load at import — file must exist for the project to run.
_TEAMS = load_teams()

# canonical team name -> location string (e.g. "Atlanta, GA", "Minnesota", "Medellin, Colombia")
TEAM_LOCATIONS: dict[str, str] = {name: info["location"] for name, info in _TEAMS.items()}

# Sorted list of canonical names (useful for tests / introspection).
CANONICAL_TEAM_NAMES: list[str] = sorted(_TEAMS.keys())
