import datetime
import pytest
from pul_normalizer.title_parser import parse_teams, load_team_index, parse_date_from_title, TeamIndex


@pytest.fixture(scope="module")
def team_index() -> TeamIndex:
    from pul_normalizer.team_registry import load_teams
    return load_team_index(load_teams())


@pytest.mark.parametrize("title,expected", [
    # Old full name forms — "Indianapolis Red" and "Nashville Nightshade" are now aliases
    ("PUL 2024 Week 3: Indianapolis Red @ Nashville Nightshade - 4/15",
     ("Indy Red", "Nashville NightShade")),

    # "vs" instead of "@"
    ("Indianapolis Red vs Nashville Nightshade - Week 3",
     ("Indy Red", "Nashville NightShade")),

    # Reversed casing
    ("indianapolis red vs nashville nightshade",
     ("Indy Red", "Nashville NightShade")),

    # Alias forms (short names)
    ("Indy Red @ Nashville Shade — Week 3",
     ("Indy Red", "Nashville NightShade")),

    # Aliases mixed with full names
    ("Surge vs Indianapolis Red",
     ("Philadelphia Surge", "Indy Red")),

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
    title = "Atlanta Soul vs Austin Torch — preview of Indy Red match"
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


@pytest.mark.parametrize("title,expected", [
    ("Atlanta SOUL @ Columbus PRIDE - 6/10/23", datetime.date(2023, 6, 10)),
    ("Indy Red vs Nashville Shade 4/15/2024 (highlights)", datetime.date(2024, 4, 15)),
    ("12/31/19 season finale", datetime.date(2019, 12, 31)),
    ("No date in this title", None),
    ("13/45/23 invalid date", None),  # month 13, day 45 — invalid
    ("Just numbers 6/10 here", None),  # missing year
])
def test_parse_date_from_title(title, expected):
    assert parse_date_from_title(title) == expected
