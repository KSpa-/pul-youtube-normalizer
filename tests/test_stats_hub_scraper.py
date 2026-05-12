from pathlib import Path
import datetime
import pytest
from stats_hub_scraper import (
    parse_schedule_html,
    week_word_to_int,
    TEAM_HOME_LOCATIONS,
    Game,
)


def test_team_home_locations_covers_all_ten_teams():
    expected = {
        "Atlanta Soul", "Austin Torch", "DC Shadow", "Indianapolis Red",
        "Milwaukee Monarchs", "Minnesota Strike", "Nashville Nightshade",
        "New York Gridlock", "Philadelphia Surge", "Raleigh Radiance",
    }
    assert set(TEAM_HOME_LOCATIONS.keys()) == expected
    for team, (city, state) in TEAM_HOME_LOCATIONS.items():
        assert city and state, f"{team} is missing city or state"


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
        assert g.away_team in TEAM_HOME_LOCATIONS
        assert g.home_team in TEAM_HOME_LOCATIONS
        assert g.away_team != g.home_team
        assert g.week >= 1
        # city/state come from home team
        expected_city, expected_state = TEAM_HOME_LOCATIONS[g.home_team]
        assert g.city == expected_city
        assert g.state == expected_state
        # venue may be None for past games
        assert g.venue is None or isinstance(g.venue, str)
