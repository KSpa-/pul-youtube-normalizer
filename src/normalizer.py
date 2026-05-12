"""Pure functions: match videos to games and build new title/description strings."""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from stats_hub_scraper import Game


MATCH_WINDOW_DAYS = 7

# PUL Stats Hub uses sentinel week numbers for postseason.
POSTSEASON_LABELS: dict[int, str] = {
    98: "Semifinals",
    99: "Finals",
}


@dataclass
class Video:
    id: str
    title: str
    description: str
    published_at: datetime.datetime
    duration_seconds: int


@dataclass
class Abbreviations:
    """Canonical full name -> short form for titles."""
    short_by_full: dict[str, str]


def load_abbreviations(path: Path) -> Abbreviations:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Abbreviations(
        short_by_full={full: meta["short"] for full, meta in raw.items()}
    )


# Match result types — use isinstance checks at call sites.

@dataclass
class Matched:
    game: Game


@dataclass
class NoMatch:
    reason: str = "no game within ±7 days for this team pair"


@dataclass
class AmbiguousMatch:
    candidates: list[Game]


MatchResult = Union[Matched, NoMatch, AmbiguousMatch]


def match_video_to_game(
    video: Video,
    team_pair: tuple[str, str],
    games: list[Game],
) -> MatchResult:
    """Find the unique game whose team pair matches (unordered) and whose
    date is within ±MATCH_WINDOW_DAYS of the video's publish date.

    Returns Matched if exactly one candidate, AmbiguousMatch if multiple,
    NoMatch if none.
    """
    published_date = video.published_at.date()
    team_set = frozenset(team_pair)
    candidates: list[Game] = []
    for g in games:
        if frozenset((g.away_team, g.home_team)) != team_set:
            continue
        if abs((published_date - g.date).days) <= MATCH_WINDOW_DAYS:
            candidates.append(g)

    if len(candidates) == 0:
        return NoMatch()
    if len(candidates) == 1:
        return Matched(candidates[0])
    return AmbiguousMatch(candidates)


def build_new_title(game: Game, abbrev: Abbreviations) -> str:
    """Build the normalized YouTube title for a game.

    Regular season: "PUL {year} W{week}: {Away} @ {Home} - {M}/{D}"
    Postseason (week 98 or 99): "PUL {year} Championship: {Round} {Away} vs {Home} - {M}/{D}"
    """
    away_short = abbrev.short_by_full[game.away_team]
    home_short = abbrev.short_by_full[game.home_team]
    month_day = f"{game.date.month}/{game.date.day}"
    if game.week in POSTSEASON_LABELS:
        round_label = POSTSEASON_LABELS[game.week]
        return f"PUL {game.season} Championship: {round_label} {away_short} vs {home_short} - {month_day}"
    return f"PUL {game.season} W{game.week}: {away_short} @ {home_short} - {month_day}"


_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def build_new_description(game: Game, abbrev: Abbreviations, template: str) -> str:
    """Build the normalized YouTube description for a game.

    Uses full team names in prose (per spec). Substitutes template placeholders:
      {GAME_DATE_LINE} {WEEK_PHRASE} {LOCATION_SENTENCE} {SEASON_YEAR}

    WEEK_PHRASE: "Week N" for regular season, "Semifinals"/"Finals" for postseason.
    LOCATION_SENTENCE drops the stadium clause if venue is None.
    """
    away_full = game.away_team
    home_full = game.home_team

    game_date_line = f"{_MONTHS[game.date.month]} {game.date.day}, {game.season}"

    if game.week in POSTSEASON_LABELS:
        week_phrase = POSTSEASON_LABELS[game.week]
    else:
        week_phrase = f"Week {game.week}"

    if game.venue is None:
        location_sentence = (
            f"Watch the {away_full} take on the {home_full} in {game.city}, {game.state}."
        )
    else:
        location_sentence = (
            f"Watch the {away_full} take on the {home_full} in {game.city}, {game.state} "
            f"at the {game.venue}."
        )

    return (
        template
        .replace("{GAME_DATE_LINE}", game_date_line)
        .replace("{WEEK_PHRASE}", week_phrase)
        .replace("{LOCATION_SENTENCE}", location_sentence)
        .replace("{SEASON_YEAR}", str(game.season))
    )
