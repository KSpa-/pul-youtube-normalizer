"""Scrape the PUL Stats Hub for schedule data.

URL pattern: https://pul-stats-hub.pages.dev/schedule/?season={YYYY}
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from team_registry import HUB_TO_CANONICAL, TEAM_LOCATIONS

# Backward-compat alias — prefer importing from team_registry directly.
TEAM_HOME_LOCATIONS = TEAM_LOCATIONS

STATS_HUB_BASE = "https://pul-stats-hub.pages.dev"
SCHEDULE_URL_TEMPLATE = STATS_HUB_BASE + "/schedule/?season={season}"

WEEK_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


class SeasonNotAvailableError(Exception):
    pass


@dataclass
class Game:
    season: int
    week: int
    date: datetime.date
    away_team: str
    home_team: str
    venue: Optional[str]
    location: str  # e.g. "Atlanta, GA", "Minnesota", "Medellin, Colombia"


def week_word_to_int(s: str) -> int:
    """Parse a week label into an integer.

    Accepts forms like "Week One", "Week 11", "week 3", "Three", or "3".
    The optional "Week" prefix is stripped before matching. Falls back to
    the first numeric run in the string. Raises ValueError if nothing parses.
    """
    s = s.strip().lower().removeprefix("week").strip()
    if s.isdigit():
        return int(s)
    if s in WEEK_WORDS:
        return WEEK_WORDS[s]
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    raise ValueError(f"Cannot parse week from {s!r}")


def parse_schedule_html(html: str, season: int) -> list[Game]:
    """Parse rendered schedule HTML into Game records.

    The Stats Hub renders season schedules as a set of week sections:

      <div data-week-season="{YYYY}" data-week-content="{N}" id="week-{YYYY}-{N}">
        ...
        <a class="game-card ..." data-away="Team Name" data-home="Team Name">
          ...
          <span class="font-display text-base text-league-gray">M/D/YYYY</span>
          ...
        </a>
        ...
      </div>

    Team identity is encoded directly in data-away / data-home attributes.
    Week number comes from data-week-content on the enclosing div.
    Date is a bare M/D/YYYY string in the first font-display span of each card.

    Non-PUL teams (Portland Rising, Columbus Pride, LA Astra, Medellin Revolution,
    etc.) are silently skipped — any team not in HUB_TO_CANONICAL is ignored.
    Venue is not present for past games in the 2024 fixture, so it is always None.
    """
    soup = BeautifulSoup(html, "html.parser")
    games: list[Game] = []

    # Each week section for the requested season
    week_sections = soup.find_all(
        attrs={"data-week-season": str(season)}
    )

    for section in week_sections:
        raw_week = section.get("data-week-content", "")
        try:
            week_num = int(raw_week)
        except (ValueError, TypeError):
            # Fallback: parse word-style week labels from section heading
            heading = section.find("h2")
            if heading:
                week_num = week_word_to_int(heading.get_text())
            else:
                continue

        for card in section.find_all(class_="game-card"):
            game = _parse_game_card(card, season=season, week=week_num)
            if game is not None:
                games.append(game)

    return games


def _parse_game_card(
    card, season: int, week: int
) -> Optional[Game]:
    """Extract a Game from a single .game-card element.

    Returns None if either team is not a recognised PUL team.
    """
    raw_away = card.get("data-away", "").strip()
    raw_home = card.get("data-home", "").strip()

    away_team = HUB_TO_CANONICAL.get(raw_away)
    home_team = HUB_TO_CANONICAL.get(raw_home)

    if away_team is None or home_team is None:
        return None

    if away_team == home_team:
        return None

    # Date is in the first span that has the font-display class and
    # looks like a date (M/D/YYYY or MM/DD/YYYY).
    date = None
    for span in card.find_all("span"):
        text = span.get_text(strip=True)
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if m:
            month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                date = datetime.date(year, month, day)
            except ValueError:
                continue
            break

    if date is None:
        return None

    location = TEAM_LOCATIONS[home_team]
    return Game(
        season=season,
        week=week,
        date=date,
        away_team=away_team,
        home_team=home_team,
        venue=None,
        location=location,
    )


def get_schedule(season: int, cache_dir: Path, refresh: bool = False) -> list[Game]:
    """Fetch (or load cached) schedule for a season.

    Raises SeasonNotAvailableError on 404 or zero-game responses.
    """
    cache_path = cache_dir / f"{season}.json"
    if cache_path.exists() and not refresh:
        return [_game_from_dict(d) for d in json.loads(cache_path.read_text(encoding="utf-8"))]

    url = SCHEDULE_URL_TEMPLATE.format(season=season)
    resp = requests.get(url, timeout=30)
    if resp.status_code == 404:
        raise SeasonNotAvailableError(f"404 for season {season} at {url}")
    resp.raise_for_status()

    games = parse_schedule_html(resp.text, season=season)
    if not games:
        raise SeasonNotAvailableError(f"Zero games parsed for season {season} from {url}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps([_game_to_dict(g) for g in games], indent=2),
        encoding="utf-8",
    )
    return games


def _game_to_dict(g: Game) -> dict:
    d = asdict(g)
    d["date"] = g.date.isoformat()
    return d


def _game_from_dict(d: dict) -> Game:
    return Game(
        season=d["season"],
        week=d["week"],
        date=datetime.date.fromisoformat(d["date"]),
        away_team=d["away_team"],
        home_team=d["home_team"],
        venue=d.get("venue"),
        location=d["location"],
    )
