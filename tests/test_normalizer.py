import datetime
from pathlib import Path
import pytest

from stats_hub_scraper import Game
from normalizer import (
    Video,
    NoMatch,
    AmbiguousMatch,
    Matched,
    match_video_to_game,
    build_new_title,
    build_new_description,
    load_abbreviations,
    POSTSEASON_LABELS,
)


def _game(season=2024, week=3, date="2024-04-15", away="Indy Red",
          home="Nashville NightShade", venue="West High School",
          location="Nashville, TN") -> Game:
    return Game(
        season=season, week=week, date=datetime.date.fromisoformat(date),
        away_team=away, home_team=home, venue=venue, location=location,
    )


def _video(video_id="v1", title="Indy Red @ Nashville Shade",
           published="2024-04-15T18:00:00Z",
           description="old description", duration_seconds=4000) -> Video:
    return Video(
        id=video_id, title=title, description=description,
        published_at=datetime.datetime.fromisoformat(published.replace("Z", "+00:00")),
        duration_seconds=duration_seconds,
    )


@pytest.fixture(scope="module")
def abbrev():
    from team_registry import TEAMS_INFO_PATH
    return load_abbreviations(TEAMS_INFO_PATH)


# --- match_video_to_game ---

def test_match_exact_date_and_teams():
    video = _video()
    games = [_game()]
    result = match_video_to_game(video, ("Indy Red", "Nashville NightShade"), games)
    assert isinstance(result, Matched)
    assert result.game is games[0]


def test_match_within_seven_day_window():
    video = _video(published="2024-04-20T18:00:00Z")
    games = [_game(date="2024-04-15")]
    result = match_video_to_game(video, ("Indy Red", "Nashville NightShade"), games)
    assert isinstance(result, Matched)


def test_match_outside_seven_day_window_returns_no_match():
    video = _video(published="2024-05-01T18:00:00Z")
    games = [_game(date="2024-04-15")]
    result = match_video_to_game(video, ("Indy Red", "Nashville NightShade"), games)
    assert isinstance(result, NoMatch)


def test_unordered_team_pair_matches():
    video = _video()
    games = [_game(away="Nashville NightShade", home="Indy Red", location="Indianapolis, IN")]
    result = match_video_to_game(video, ("Indy Red", "Nashville NightShade"), games)
    assert isinstance(result, Matched)


def test_ambiguous_when_two_games_within_window():
    video = _video()
    games = [
        _game(date="2024-04-15"),
        _game(date="2024-04-16"),
    ]
    result = match_video_to_game(video, ("Indy Red", "Nashville NightShade"), games)
    assert isinstance(result, AmbiguousMatch)
    assert len(result.candidates) == 2


# --- build_new_title: regular season ---

def test_build_new_title_uses_short_names_and_slash_date(abbrev):
    g = _game()
    assert build_new_title(g, abbrev) == "PUL 2024 W3: Indy Red @ Nashville Shade - 4/15"


def test_build_new_title_strips_leading_zeros(abbrev):
    g = _game(date="2024-05-04", week=7)
    assert build_new_title(g, abbrev) == "PUL 2024 W7: Indy Red @ Nashville Shade - 5/4"


# --- build_new_title: postseason ---

def test_postseason_labels_constant():
    assert POSTSEASON_LABELS[98] == "Semifinals"
    assert POSTSEASON_LABELS[99] == "Finals"


def test_build_new_title_semifinals(abbrev):
    g = _game(week=98, date="2024-06-15")
    assert build_new_title(g, abbrev) == "PUL 2024 Championship: Semifinals Indy Red vs Nashville Shade - 6/15"


def test_build_new_title_finals(abbrev):
    g = _game(week=99, date="2024-06-22")
    assert build_new_title(g, abbrev) == "PUL 2024 Championship: Finals Indy Red vs Nashville Shade - 6/22"


# --- build_new_description: regular season ---

def test_build_new_description_full(abbrev):
    g = _game()
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "April 15, 2024" in out
    assert "Week 3 of the 2024 PUL season." in out
    assert "Watch the Indy Red take on the Nashville NightShade" in out
    assert "in Nashville, TN at the West High School." in out
    assert "The 2024 season schedule and stats can be found here:" in out


def test_build_new_description_drops_stadium_when_venue_missing(abbrev):
    g = _game(venue=None)
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "Watch the Indy Red take on the Nashville NightShade in Nashville, TN." in out
    assert "at the " not in out


# --- build_new_description: postseason ---

def test_build_new_description_semifinals(abbrev):
    g = _game(week=98, date="2024-06-15", venue=None)
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "Semifinals of the 2024 PUL season." in out
    assert "Week 98" not in out


def test_build_new_description_finals(abbrev):
    g = _game(week=99, date="2024-06-22", venue=None)
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "Finals of the 2024 PUL season." in out
    assert "Week 99" not in out
