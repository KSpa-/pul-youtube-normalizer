"""Canonical PUL team registry loaded from data/teams_info.json.

This module is the single source of truth for team names, locations, short
forms, aliases, and Stats Hub spellings. The scraper, title parser, and
normalizer all derive their team data from here.
"""
from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEAMS_INFO_PATH = PROJECT_ROOT / "data" / "teams_info.json"


def load_teams(path: Path = TEAMS_INFO_PATH) -> dict[str, dict]:
    """Return mapping of canonical team name -> team info dict."""
    return json.loads(path.read_text(encoding="utf-8"))


# Eagerly load at import — file ships with the repo and must exist to run.
_TEAMS = load_teams()

# canonical team name -> location string (e.g. "Atlanta, GA", "Minnesota", "Medellin, Colombia")
TEAM_LOCATIONS: dict[str, str] = {name: info["location"] for name, info in _TEAMS.items()}

# Sorted list of canonical names (useful for tests / introspection).
CANONICAL_TEAM_NAMES: list[str] = sorted(_TEAMS.keys())

# Every team string the Stats Hub uses (data-away / data-home attributes)
# -> canonical name. Each canonical name maps to itself, plus any legacy
# spellings listed in the team's `hub_names`.
HUB_TO_CANONICAL: dict[str, str] = {name: name for name in _TEAMS}
for _name, _info in _TEAMS.items():
    for _hub_name in _info.get("hub_names", []):
        HUB_TO_CANONICAL[_hub_name] = _name
