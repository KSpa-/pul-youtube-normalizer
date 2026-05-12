import json
from pathlib import Path
import pytest
from title_parser import parse_teams, load_team_index, TeamIndex


@pytest.fixture(scope="module")
def team_index() -> TeamIndex:
    raw = json.loads(Path("team_abbreviations.json").read_text(encoding="utf-8"))
    return load_team_index(raw)


@pytest.mark.parametrize("title,expected", [
    # Canonical form with @
    ("PUL 2024 Week 3: Indianapolis Red @ Nashville Nightshade - 4/15",
     ("Indianapolis Red", "Nashville Nightshade")),

    # "vs" instead of "@"
    ("Indianapolis Red vs Nashville Nightshade - Week 3",
     ("Indianapolis Red", "Nashville Nightshade")),

    # Reversed casing
    ("indianapolis red vs nashville nightshade",
     ("Indianapolis Red", "Nashville Nightshade")),

    # Alias forms
    ("Indy Red @ Nashville Shade — Week 3",
     ("Indianapolis Red", "Nashville Nightshade")),

    # Aliases mixed with full names
    ("Surge vs Indianapolis Red",
     ("Philadelphia Surge", "Indianapolis Red")),

    # Two short aliases
    ("NY Gridlock @ Philly Surge - playoff",
     ("New York Gridlock", "Philadelphia Surge")),
])
def test_parse_two_teams(team_index, title, expected):
    assert parse_teams(title, team_index) == expected


def test_returns_none_when_zero_teams(team_index):
    assert parse_teams("PUL Highlights — Best Plays of 2024", team_index) is None


def test_returns_none_when_only_one_team(team_index):
    assert parse_teams("Atlanta Soul: Season Recap", team_index) is None


def test_returns_first_two_when_more_than_two_mentioned(team_index):
    # Should return the first two distinct teams in order of appearance
    title = "Atlanta Soul vs Austin Torch — preview of Indianapolis Red match"
    assert parse_teams(title, team_index) == ("Atlanta Soul", "Austin Torch")


def test_load_team_index_builds_alias_map():
    raw = {
        "Atlanta Soul": {"short": "Atlanta Soul", "aliases": ["Soul", "ATL"]},
    }
    idx = load_team_index(raw)
    assert "atlanta soul" in idx.canonical_by_lower
    assert "soul" in idx.canonical_by_lower
    assert "atl" in idx.canonical_by_lower
    assert idx.canonical_by_lower["soul"] == "Atlanta Soul"
