"""Pure functions: match videos to games and build new title/description strings."""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .stats_hub_scraper import Game


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


def abbreviations_from_teams(raw: dict) -> Abbreviations:
    """Build an Abbreviations record from raw team registry data.

    The JSON shape is `{canonical_full_name: {"short": str, ...}}`.
    Only the `short` field is used here; aliases are consumed by title_parser.
    """
    return Abbreviations(
        short_by_full={full: meta["short"] for full, meta in raw.items()}
    )


def load_abbreviations(path: Path) -> Abbreviations:
    """Load a team registry JSON file and return an Abbreviations record.

    Raises FileNotFoundError / json.JSONDecodeError / KeyError on bad input.
    """
    return abbreviations_from_teams(json.loads(path.read_text(encoding="utf-8")))


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
    match_date: datetime.date | None = None,
    window_days: int = MATCH_WINDOW_DAYS,
) -> MatchResult:
    """Find the unique game whose team pair matches (unordered) and whose
    date is within ±window_days of the reference date.

    The reference date is `match_date` if provided (e.g., extracted from the
    title), otherwise the video's `published_at` date. A title-extracted date
    is far more accurate than `publishedAt` (which lags by upload/edit time),
    so the caller should pass a tight `window_days` (e.g., 2) when it provides
    `match_date`, and a wider one (e.g., 14) when falling back to publishedAt.

    Returns Matched if exactly one candidate, AmbiguousMatch if multiple,
    NoMatch if none.
    """
    ref_date = match_date if match_date is not None else video.published_at.date()
    team_set = frozenset(team_pair)
    candidates: list[Game] = []
    for g in games:
        if frozenset((g.away_team, g.home_team)) != team_set:
            continue
        if abs((ref_date - g.date).days) <= window_days:
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
            f"Watch the {away_full} take on the {home_full} in {game.location}."
        )
    else:
        location_sentence = (
            f"Watch the {away_full} take on the {home_full} in {game.location} "
            f"at the {game.venue}."
        )

    return (
        template
        .replace("{GAME_DATE_LINE}", game_date_line)
        .replace("{WEEK_PHRASE}", week_phrase)
        .replace("{LOCATION_SENTENCE}", location_sentence)
        .replace("{SEASON_YEAR}", str(game.season))
    )
