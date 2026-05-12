from pathlib import Path
import datetime
import pytest
from stats_hub_scraper import (
    parse_schedule_html,
    week_word_to_int,
    Game,
)
from team_registry import TEAM_LOCATIONS


def test_team_home_locations_covers_all_pul_teams():
    expected = {
        "Atlanta Soul", "Austin Torch", "Columbus Pride", "DC Shadow",
        "Indy Red", "LA Astra", "Medellin Revolution", "Milwaukee Monarchs",
        "Minnesota Strike", "Nashville NightShade", "New York Gridlock",
        "Philadelphia Surge", "Portland Rising", "Raleigh Radiance",
    }
    assert set(TEAM_LOCATIONS.keys()) == expected
    for team, location in TEAM_LOCATIONS.items():
        assert location, f"{team} is missing location"


@pytest.mark.parametrize("word,expected", [
    ("Week One", 1),
    ("Week Two", 2),
    ("Week Three", 3),
    ("Week Four", 4),
    ("Week Five", 5),
    ("Week Six", 6),
    ("Week Seven", 7),
    ("Week Eight", 8),
    ("Week Nine", 9),
    ("Week Ten", 10),
    ("Week 11", 11),
    ("week 3", 3),
])
def test_week_word_to_int(word, expected):
    assert week_word_to_int(word) == expected


def test_parse_schedule_html_extracts_games():
    html = Path("tests/fixtures/schedule_2024.html").read_text(encoding="utf-8")
    games = parse_schedule_html(html, season=2024)

    # Sanity bounds — should be at least a handful of games and not absurd
    assert 5 < len(games) < 200

    # Every game has required fields
    for g in games:
        assert isinstance(g, Game)
        assert g.season == 2024
        assert isinstance(g.date, datetime.date)
        assert g.away_team in TEAM_LOCATIONS
        assert g.home_team in TEAM_LOCATIONS
        assert g.away_team != g.home_team
        assert g.week >= 1
        # location comes from home team
        assert g.location == TEAM_LOCATIONS[g.home_team]
        assert g.location, f"Game {g} has empty location"
        # venue may be None for past games
        assert g.venue is None or isinstance(g.venue, str)
