# PUL YouTube Normalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that normalizes full-game video titles and descriptions on the PUL YouTube channel using the PUL Stats Hub as the authoritative schedule source, with dry-run preview and manual-review logging.

**Architecture:** Modular Python package — pure-logic modules (`title_parser`, `normalizer`) are unit-tested in isolation; I/O modules (`stats_hub_scraper`, `youtube_client`, `auth`) are tested with HTML fixtures or mocks. A single `cli.py` wires them together. Stats hub data is scraped once per season and cached to JSON.

**Tech Stack:** Python 3.11+, `google-auth-oauthlib`, `google-api-python-client`, `requests`, `beautifulsoup4`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-05-12-pul-youtube-normalizer-design.md`

---

## File map

```
youtube_normalization_project/
├── .gitignore                  (Task 1)
├── README.md                   (Task 1)
├── requirements.txt            (Task 1)
├── pytest.ini                  (Task 1)
├── client_secrets.json         (user-supplied; existing as client_secrets.json.json)
├── token.json                  (generated at runtime; gitignored)
├── team_abbreviations.json     (Task 2)
├── description_template.txt    (Task 2)
├── schedule_cache/             (gitignored; runtime)
├── logs/                       (gitignored; runtime)
├── src/
│   ├── __init__.py             (Task 1)
│   ├── title_parser.py         (Task 3)
│   ├── stats_hub_scraper.py    (Task 4 — owns Game dataclass + TEAM_HOME_LOCATIONS)
│   ├── normalizer.py           (Task 5)
│   ├── auth.py                 (Task 6)
│   ├── youtube_client.py       (Task 7)
│   └── cli.py                  (Task 8)
└── tests/
    ├── __init__.py             (Task 1)
    ├── fixtures/
    │   └── schedule_2024.html  (Task 4 — recorded HTML)
    ├── test_title_parser.py    (Task 3)
    ├── test_stats_hub_scraper.py (Task 4)
    └── test_normalizer.py      (Task 5)
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`, `README.md`, `requirements.txt`, `pytest.ini`, `src/__init__.py`, `tests/__init__.py`, `tests/fixtures/.gitkeep`, `schedule_cache/.gitkeep`, `logs/.gitkeep`
- Rename: `client_secrets.json.json` → `client_secrets.json`

- [ ] **Step 1: Initialize git repository**

Run from the project root:
```powershell
git init
git branch -M main
```

- [ ] **Step 2: Rename the credentials file**

The file currently has a double extension.
```powershell
Rename-Item client_secrets.json.json client_secrets.json
```

If the file is not present, skip — script will error with a clear message at first run.

- [ ] **Step 3: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/

# Project secrets / runtime artifacts
client_secrets.json
token.json
schedule_cache/*.json
logs/*.log

# Keep directory placeholders
!schedule_cache/.gitkeep
!logs/.gitkeep
!tests/fixtures/.gitkeep
```

- [ ] **Step 4: Create `requirements.txt`**

```
google-auth-oauthlib==1.2.1
google-api-python-client==2.149.0
requests==2.32.3
beautifulsoup4==4.12.3
pytest==8.3.3
```

- [ ] **Step 5: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = src
python_files = test_*.py
```

- [ ] **Step 6: Create `README.md`**

```markdown
# PUL YouTube Normalizer

Normalizes titles and descriptions of full-game videos on the PUL YouTube channel.

## Setup

1. Place your OAuth client secrets JSON at `client_secrets.json` (download from Google Cloud Console).
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (mac/linux).
3. `pip install -r requirements.txt`.

## Usage

Dry-run (default — no writes):
```
python -m src.cli --dry-run
```

Apply changes (requires interactive `y/N` confirmation):
```
python -m src.cli --apply
```

See `docs/superpowers/specs/2026-05-12-pul-youtube-normalizer-design.md` for full design.
```

- [ ] **Step 7: Create empty package and placeholder files**

```powershell
New-Item -ItemType File src\__init__.py
New-Item -ItemType File tests\__init__.py
New-Item -ItemType Directory tests\fixtures, schedule_cache, logs
New-Item -ItemType File tests\fixtures\.gitkeep, schedule_cache\.gitkeep, logs\.gitkeep
```

- [ ] **Step 8: Install dependencies and verify pytest runs**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

Expected: pytest exits 5 ("no tests ran"). That's fine — confirms pytest is installed.

- [ ] **Step 9: Commit**

```powershell
git add .gitignore README.md requirements.txt pytest.ini src/ tests/ schedule_cache/.gitkeep logs/.gitkeep docs/
git commit -m "chore: project scaffolding"
```

Note: do NOT add `client_secrets.json` or `token.json` to commits — `.gitignore` covers them.

---

## Task 2: Seed configuration files

**Files:**
- Create: `team_abbreviations.json`, `description_template.txt`

- [ ] **Step 1: Create `team_abbreviations.json`**

```json
{
  "Atlanta Soul":         {"short": "Atlanta Soul",       "aliases": ["Soul", "ATL Soul", "ATL"]},
  "Austin Torch":         {"short": "Austin Torch",       "aliases": ["Torch", "AUS Torch", "AUS"]},
  "DC Shadow":            {"short": "DC Shadow",          "aliases": ["Shadow", "Washington Shadow", "DC"]},
  "Indianapolis Red":     {"short": "Indy Red",           "aliases": ["Indy Red", "Indianapolis", "IND"]},
  "Milwaukee Monarchs":   {"short": "Milwaukee Monarchs", "aliases": ["Monarchs", "MIL Monarchs", "MIL"]},
  "Minnesota Strike":     {"short": "Minn Strike",        "aliases": ["Strike", "MN Strike", "Minnesota", "MIN"]},
  "Nashville Nightshade": {"short": "Nashville Shade",    "aliases": ["Nightshade", "Shade", "NSH Nightshade", "NSH"]},
  "New York Gridlock":    {"short": "NY Gridlock",        "aliases": ["Gridlock", "NYC Gridlock", "NY", "NYC"]},
  "Philadelphia Surge":   {"short": "Philly Surge",       "aliases": ["Surge", "Philly Surge", "Philadelphia", "PHI"]},
  "Raleigh Radiance":     {"short": "Raleigh Radiance",   "aliases": ["Radiance", "RAL Radiance", "RAL"]}
}
```

- [ ] **Step 2: Create `description_template.txt`**

The `{LOCATION_SENTENCE}` placeholder gets replaced per video. Everything else is fixed text. `{SeasonYear}` is replaced per video.

```
{GAME_DATE_LINE}
Week {WEEK_NUMBER} of the {SEASON_YEAR} PUL season. {LOCATION_SENTENCE}


About the PUL:

The Premier Ultimate League (PUL), founded in 2019, is the professional ultimate league for women and gender-expansive athletes that operates as a 501c6 nonprofit. Since the PUL's founding, the league and its teams actively strive to create an inclusive and competitive league showcasing athleticism and the game's spirit. The PUL has 10 member teams: Atlanta Soul, Austin Torch, DC Shadow, Indianapolis Red, Milwaukee Monarchs, Minnesota Strike, Nashville Nightshade, New York Gridlock, Philadelphia Surge, and Raleigh Radiance. These 10 teams compete in regular season play from April to June, with the championship taking place in June. In addition to all 10 teams highlighting athleticism and ultimate at its highest peak of competition, the PUL strives for gender, racial, and economic diversity.

The {SEASON_YEAR} season schedule and stats can be found here: https://pul-stats-hub.pages.dev/

The PUL can be followed on social media at @premierultimateleague on Facebook, Instagram, LinkedIn, and YouTube.

Like us on Facebook:  https://www.facebook.com/premierultimateleague
Follow us on Instagram:  https://www.instagram.com/premierultimateleague
Shop for PUL Gear: https://teams.breakmark.com/group/pul
```

- [ ] **Step 3: Commit**

```powershell
git add team_abbreviations.json description_template.txt
git commit -m "feat: seed team abbreviations and description template"
```

---

## Task 3: `title_parser` module (TDD)

**Files:**
- Create: `tests/test_title_parser.py`, `src/title_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_title_parser.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
pytest tests/test_title_parser.py -v
```

Expected: ImportError / ModuleNotFoundError for `title_parser`.

- [ ] **Step 3: Implement `src/title_parser.py`**

```python
"""Parse messy current YouTube titles to extract the two team names.

Does NOT extract date, week, or home/away — those come from the stats hub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TeamIndex:
    """Lowercase name/alias -> canonical full team name, plus sorted name list."""
    canonical_by_lower: dict[str, str]
    # Names sorted longest-first so longer aliases match before shorter substrings
    # (e.g., "Atlanta Soul" matches before bare "Soul").
    names_longest_first: list[str]


def load_team_index(raw: dict) -> TeamIndex:
    canonical_by_lower: dict[str, str] = {}
    for full_name, meta in raw.items():
        canonical_by_lower[full_name.lower()] = full_name
        for alias in meta.get("aliases", []):
            canonical_by_lower[alias.lower()] = full_name
    names = sorted(canonical_by_lower.keys(), key=len, reverse=True)
    return TeamIndex(canonical_by_lower=canonical_by_lower, names_longest_first=names)


def parse_teams(title: str, idx: TeamIndex) -> Optional[tuple[str, str]]:
    """Return (first_team, second_team) by order of appearance in the title.

    Returns None if fewer than 2 distinct teams found.
    """
    haystack = title.lower()
    # Track each (start_index, canonical_name); claim characters so we don't match
    # overlapping aliases (e.g., "Indy Red" shouldn't also match a separate "Red").
    claimed = [False] * len(haystack)
    found: list[tuple[int, str]] = []

    for name in idx.names_longest_first:
        # Word-boundary-ish match to avoid partials like "ATL" matching inside "atlas"
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        for m in re.finditer(pattern, haystack):
            start, end = m.span()
            if any(claimed[start:end]):
                continue
            for i in range(start, end):
                claimed[i] = True
            canonical = idx.canonical_by_lower[name]
            # Skip duplicate canonical (e.g., "Indy Red" and "Indianapolis Red" both matched)
            if any(canonical == c for _, c in found):
                continue
            found.append((start, canonical))

    found.sort(key=lambda pair: pair[0])
    if len(found) < 2:
        return None
    return (found[0][1], found[1][1])
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_title_parser.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/title_parser.py tests/test_title_parser.py
git commit -m "feat: title parser with alias-aware team extraction"
```

---

## Task 4: `stats_hub_scraper` module (TDD with HTML fixture)

**Files:**
- Create: `tests/fixtures/schedule_2024.html`, `tests/test_stats_hub_scraper.py`, `src/stats_hub_scraper.py`

- [ ] **Step 1: Identify the stats-hub URL pattern and record a fixture**

This step is **manual investigation** (the spec flags this as an open issue). Do the following in a browser:

1. Open `https://pul-stats-hub.pages.dev/schedule`.
2. Click the season selector and choose **2024**.
3. Note the URL after selection (likely `/schedule?season=2024` or similar). Record this pattern.
4. Save the rendered HTML: right-click → Save Page As → save to `tests/fixtures/schedule_2024.html` (HTML only, no assets).
5. Confirm the file has actual game rows in it (search for team names like "Atlanta Soul").

Record the URL pattern in a comment at the top of `src/stats_hub_scraper.py` in step 3.

- [ ] **Step 2: Write failing tests**

Create `tests/test_stats_hub_scraper.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
pytest tests/test_stats_hub_scraper.py -v
```

Expected: ImportError for `stats_hub_scraper`.

- [ ] **Step 4: Implement `src/stats_hub_scraper.py`**

The HTML parser logic depends on the actual structure of the saved fixture. **Read the fixture HTML** and identify which CSS selectors locate game rows, team names, dates, week, and venue. The skeleton below shows the public API and the bits that don't depend on the markup — fill in `_parse_game_row` based on the fixture.

```python
"""Scrape the PUL Stats Hub for schedule data.

URL pattern discovered during Task 4 step 1: <FILL IN ACTUAL PATTERN>
e.g., https://pul-stats-hub.pages.dev/schedule?season=2024
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


STATS_HUB_BASE = "https://pul-stats-hub.pages.dev"
SCHEDULE_URL_TEMPLATE = STATS_HUB_BASE + "/schedule?season={season}"  # adjust if pattern differs

TEAM_HOME_LOCATIONS: dict[str, tuple[str, str]] = {
    "Atlanta Soul":         ("Atlanta", "GA"),
    "Austin Torch":         ("Austin", "TX"),
    "DC Shadow":            ("Washington", "DC"),
    "Indianapolis Red":     ("Indianapolis", "IN"),
    "Milwaukee Monarchs":   ("Milwaukee", "WI"),
    "Minnesota Strike":     ("Minneapolis", "MN"),
    "Nashville Nightshade": ("Nashville", "TN"),
    "New York Gridlock":    ("New York", "NY"),
    "Philadelphia Surge":   ("Philadelphia", "PA"),
    "Raleigh Radiance":     ("Raleigh", "NC"),
}

WEEK_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}

# Map team strings as they appear in the stats hub (abbreviations or short forms)
# to our canonical full team names. Fill in once you've seen the fixture HTML.
HUB_TO_CANONICAL: dict[str, str] = {
    # examples — verify against actual HTML:
    # "ATL": "Atlanta Soul",
    # "Atlanta Soul": "Atlanta Soul",
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
    city: str
    state: str


def week_word_to_int(s: str) -> int:
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
    """Parse the rendered schedule HTML into Game records.

    Implementation notes — fill in after inspecting tests/fixtures/schedule_2024.html:
      - Identify the container element for the schedule (e.g., a table or list of rows).
      - For each game row: extract date, week, away team text, home team text,
        and venue text if present.
      - Map team text through HUB_TO_CANONICAL to canonical names.
      - Derive city/state from TEAM_HOME_LOCATIONS[home_team].
    """
    soup = BeautifulSoup(html, "html.parser")
    games: list[Game] = []

    # === REPLACE THIS BLOCK with selectors based on the fixture ===
    rows = soup.select("REPLACE_WITH_ACTUAL_SELECTOR")
    for row in rows:
        game = _parse_game_row(row, season)
        if game is not None:
            games.append(game)
    # === END REPLACE BLOCK ===

    return games


def _parse_game_row(row, season: int) -> Optional[Game]:
    """Parse a single row element into a Game, or None if the row is malformed."""
    # FILL IN after inspecting fixture.
    raise NotImplementedError(
        "Implement _parse_game_row based on tests/fixtures/schedule_2024.html structure"
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
        city=d["city"],
        state=d["state"],
    )
```

- [ ] **Step 5: Fill in the selectors and `_parse_game_row`**

Open `tests/fixtures/schedule_2024.html` and identify:
1. The CSS selector for game rows (e.g., `div.schedule-row`, `tr.game`, etc.).
2. Sub-selectors for each field (date, week, away team, home team, venue).

Replace the `REPLACE_WITH_ACTUAL_SELECTOR` and implement `_parse_game_row`. Populate `HUB_TO_CANONICAL` based on the team identifiers used in the HTML (the stats hub uses abbreviations next to logos, per the WebFetch investigation).

If any team string in the HTML isn't in `HUB_TO_CANONICAL`, `_parse_game_row` should `raise ValueError(f"Unknown team string: {s!r}")` rather than silently dropping — surfaces the mismatch immediately.

- [ ] **Step 6: Run tests to verify they pass**

```powershell
pytest tests/test_stats_hub_scraper.py -v
```

Expected: all tests pass. If the fixture-driven test fails because the HTML uses unexpected selectors, iterate on `_parse_game_row` until it passes.

- [ ] **Step 7: Commit**

```powershell
git add src/stats_hub_scraper.py tests/test_stats_hub_scraper.py tests/fixtures/schedule_2024.html
git commit -m "feat: stats hub scraper with cached per-season schedules"
```

---

## Task 5: `normalizer` module (TDD)

**Files:**
- Create: `tests/test_normalizer.py`, `src/normalizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_normalizer.py`:

```python
import datetime
import json
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
)


def _game(season=2024, week=3, date="2024-04-15", away="Indianapolis Red",
          home="Nashville Nightshade", venue="West High School",
          city="Nashville", state="TN") -> Game:
    return Game(
        season=season, week=week, date=datetime.date.fromisoformat(date),
        away_team=away, home_team=home, venue=venue, city=city, state=state,
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
    return load_abbreviations(Path("team_abbreviations.json"))


def test_match_exact_date_and_teams():
    video = _video()
    games = [_game()]
    result = match_video_to_game(video, ("Indianapolis Red", "Nashville Nightshade"), games)
    assert isinstance(result, Matched)
    assert result.game is games[0]


def test_match_within_seven_day_window():
    video = _video(published="2024-04-20T18:00:00Z")
    games = [_game(date="2024-04-15")]
    result = match_video_to_game(video, ("Indianapolis Red", "Nashville Nightshade"), games)
    assert isinstance(result, Matched)


def test_match_outside_seven_day_window_returns_no_match():
    video = _video(published="2024-05-01T18:00:00Z")
    games = [_game(date="2024-04-15")]
    result = match_video_to_game(video, ("Indianapolis Red", "Nashville Nightshade"), games)
    assert isinstance(result, NoMatch)


def test_unordered_team_pair_matches():
    video = _video()
    games = [_game(away="Nashville Nightshade", home="Indianapolis Red")]
    # Parser returned them in title order, hub has them in opposite order
    result = match_video_to_game(video, ("Indianapolis Red", "Nashville Nightshade"), games)
    assert isinstance(result, Matched)


def test_ambiguous_when_two_games_within_window():
    video = _video()
    games = [
        _game(date="2024-04-15"),
        _game(date="2024-04-16"),  # rematch within window
    ]
    result = match_video_to_game(video, ("Indianapolis Red", "Nashville Nightshade"), games)
    assert isinstance(result, AmbiguousMatch)
    assert len(result.candidates) == 2


def test_build_new_title_uses_short_names_and_slash_date(abbrev):
    g = _game()
    assert build_new_title(g, abbrev) == "PUL 2024 W3: Indy Red @ Nashville Shade - 4/15"


def test_build_new_title_strips_leading_zeros(abbrev):
    g = _game(date="2024-05-04", week=7)
    assert build_new_title(g, abbrev) == "PUL 2024 W7: Indy Red @ Nashville Shade - 5/4"


def test_build_new_description_full(abbrev):
    g = _game()
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "April 15, 2024" in out
    assert "Week 3 of the 2024 PUL season." in out
    assert "Watch the Indianapolis Red take on the Nashville Nightshade" in out
    assert "in Nashville, TN at the West High School." in out
    assert "The 2024 season schedule and stats can be found here:" in out


def test_build_new_description_drops_stadium_when_venue_missing(abbrev):
    g = _game(venue=None)
    template = Path("description_template.txt").read_text(encoding="utf-8")
    out = build_new_description(g, abbrev, template)
    assert "Watch the Indianapolis Red take on the Nashville Nightshade in Nashville, TN." in out
    assert "at the " not in out  # stadium phrase absent
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/test_normalizer.py -v
```

Expected: ImportError for `normalizer`.

- [ ] **Step 3: Implement `src/normalizer.py`**

```python
"""Pure functions: match videos to games and build new title/description strings."""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from stats_hub_scraper import Game


MATCH_WINDOW_DAYS = 7


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
    away_short = abbrev.short_by_full[game.away_team]
    home_short = abbrev.short_by_full[game.home_team]
    month_day = f"{game.date.month}/{game.date.day}"
    return f"PUL {game.season} W{game.week}: {away_short} @ {home_short} - {month_day}"


_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def build_new_description(game: Game, abbrev: Abbreviations, template: str) -> str:
    # Full names in description (per design)
    away_full = game.away_team
    home_full = game.home_team

    game_date_line = f"{_MONTHS[game.date.month]} {game.date.day}, {game.season}"

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
        .replace("{WEEK_NUMBER}", str(game.week))
        .replace("{LOCATION_SENTENCE}", location_sentence)
        .replace("{SEASON_YEAR}", str(game.season))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_normalizer.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/normalizer.py tests/test_normalizer.py
git commit -m "feat: normalizer with match logic and title/description builders"
```

---

## Task 6: `auth` module

**Files:**
- Create: `src/auth.py`

No automated tests — OAuth requires browser interaction. Manual verification at end.

- [ ] **Step 1: Implement `src/auth.py`**

```python
"""OAuth2 flow for YouTube Data API."""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKEN_PATH = Path("token.json")
CLIENT_SECRETS_CANDIDATES = [Path("client_secrets.json"), Path("client_secrets.json.json")]


class CredentialsNotFound(RuntimeError):
    pass


def _find_client_secrets() -> Path:
    for p in CLIENT_SECRETS_CANDIDATES:
        if p.exists():
            if p.name == "client_secrets.json.json":
                print(
                    "WARNING: found 'client_secrets.json.json' (double extension). "
                    "Consider renaming to 'client_secrets.json'."
                )
            return p
    raise CredentialsNotFound(
        "No client_secrets.json found. Download OAuth client credentials from "
        "Google Cloud Console and save as ./client_secrets.json."
    )


def get_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        return creds

    secrets_path = _find_client_secrets()
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds
```

- [ ] **Step 2: Manual smoke test**

```powershell
python -c "from src.auth import get_credentials; c = get_credentials(); print('OK', bool(c.valid))"
```

Expected on first run: a browser window opens for Google OAuth consent. After granting, terminal prints `OK True` and `token.json` is created. Subsequent runs use the saved token (no browser).

- [ ] **Step 3: Commit**

```powershell
git add src/auth.py
git commit -m "feat: OAuth2 authentication with token persistence"
```

---

## Task 7: `youtube_client` module

**Files:**
- Create: `src/youtube_client.py`

Light testing here is fine — most logic is API plumbing. Add one unit test for the duration parser.

- [ ] **Step 1: Write failing test for duration parser**

Add to `tests/test_youtube_client.py` (create file):

```python
import pytest
from youtube_client import parse_iso8601_duration


@pytest.mark.parametrize("s,expected_seconds", [
    ("PT1H", 3600),
    ("PT1H30M", 5400),
    ("PT59M59S", 3599),
    ("PT1H0M0S", 3600),
    ("PT2H15M30S", 8130),
    ("PT45S", 45),
])
def test_parse_iso8601_duration(s, expected_seconds):
    assert parse_iso8601_duration(s) == expected_seconds
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pytest tests/test_youtube_client.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `src/youtube_client.py`**

```python
"""YouTube Data API v3 wrapper for listing/updating videos."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from normalizer import Video  # Reuse the Video dataclass for consistency
import datetime


FULL_GAME_MIN_SECONDS = 3600  # > 1 hour
MAX_RETRIES = 5


def parse_iso8601_duration(s: str) -> int:
    """Parse YouTube's ISO 8601 duration like 'PT1H30M15S' to total seconds.

    Only handles H/M/S — YouTube videos don't use D/Y components in duration.
    """
    m = re.fullmatch(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?", s
    )
    if not m:
        raise ValueError(f"Unrecognized ISO 8601 duration: {s!r}")
    h = int(m.group("h") or 0)
    mins = int(m.group("m") or 0)
    secs = int(m.group("s") or 0)
    return h * 3600 + mins * 60 + secs


def _call_with_retry(request_callable):
    """Run a `request.execute()`-style callable with exponential backoff on 5xx/429."""
    delay = 1
    for attempt in range(MAX_RETRIES):
        try:
            return request_callable()
        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else 0
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise


def build_service(creds: Credentials):
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def list_my_full_game_videos(service) -> Iterator[Video]:
    """Yield every video on the authenticated user's channel longer than 1 hour."""
    # 1. Get the uploads playlist ID for "mine".
    channels = _call_with_retry(
        lambda: service.channels().list(part="contentDetails", mine=True).execute()
    )
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authenticated user.")
    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2. Paginate playlist items to collect video IDs.
    video_ids: list[str] = []
    page_token: str | None = None
    while True:
        page = _call_with_retry(
            lambda: service.playlistItems()
            .list(
                part="contentDetails",
                playlistId=uploads_playlist,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )
        for item in page.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    # 3. Batch videos.list (50 ids per call) to get snippet + contentDetails.
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = _call_with_retry(
            lambda: service.videos()
            .list(part="snippet,contentDetails", id=",".join(batch))
            .execute()
        )
        for v in resp.get("items", []):
            duration_seconds = parse_iso8601_duration(v["contentDetails"]["duration"])
            if duration_seconds < FULL_GAME_MIN_SECONDS:
                continue
            snippet = v["snippet"]
            yield Video(
                id=v["id"],
                title=snippet["title"],
                description=snippet.get("description", ""),
                published_at=datetime.datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                ),
                duration_seconds=duration_seconds,
            )


def update_video(service, video_id: str, new_title: str, new_description: str,
                 current_snippet: dict | None = None) -> dict:
    """Push title/description to YouTube. Requires the current snippet to preserve
    category/tags/etc. that we're not changing.
    """
    if current_snippet is None:
        resp = _call_with_retry(
            lambda: service.videos().list(part="snippet", id=video_id).execute()
        )
        items = resp.get("items", [])
        if not items:
            raise RuntimeError(f"Video {video_id} not found.")
        current_snippet = items[0]["snippet"]

    new_snippet = dict(current_snippet)
    new_snippet["title"] = new_title
    new_snippet["description"] = new_description

    return _call_with_retry(
        lambda: service.videos()
        .update(part="snippet", body={"id": video_id, "snippet": new_snippet})
        .execute()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/test_youtube_client.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/youtube_client.py tests/test_youtube_client.py
git commit -m "feat: youtube client with list/update and retry"
```

---

## Task 8: `cli` module

**Files:**
- Create: `src/cli.py`

- [ ] **Step 1: Implement `src/cli.py`**

```python
"""Command-line entry point for the PUL YouTube normalizer."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from auth import get_credentials
from normalizer import (
    AmbiguousMatch,
    Matched,
    NoMatch,
    Video,
    build_new_description,
    build_new_title,
    load_abbreviations,
    match_video_to_game,
)
from stats_hub_scraper import (
    Game,
    SeasonNotAvailableError,
    get_schedule,
)
from title_parser import load_team_index, parse_teams
from youtube_client import build_service, list_my_full_game_videos, update_video


SCHEDULE_CACHE_DIR = Path("schedule_cache")
LOG_DIR_DEFAULT = Path("logs")
TEAM_ABBREVIATIONS_PATH = Path("team_abbreviations.json")
DESCRIPTION_TEMPLATE_PATH = Path("description_template.txt")


def _log_manual_review(log_dir: Path, *, video: Video, reason: str, details: str = "") -> None:
    entry = {
        "video_id": video.id,
        "title": video.title,
        "publishedAt": video.published_at.isoformat(),
        "reason": reason,
        "details": details,
    }
    with (log_dir / "manual_review.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _log_dry_run(log_dir: Path, *, video: Video, new_title: str) -> None:
    line = f"{video.id} | {video.title}  ->  {new_title}\n"
    with (log_dir / "dry_run.log").open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def _log_description_change(log_dir: Path, *, video: Video, new_description: str) -> None:
    sep = "\n" + ("=" * 60) + "\n"
    with (log_dir / "description_changes.log").open("a", encoding="utf-8") as f:
        f.write(f"{sep}{video.id} | {video.title}\n--- OLD ---\n")
        f.write(video.description + "\n--- NEW ---\n")
        f.write(new_description + "\n")


def _ensure_clean_log_dir(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    for name in ("dry_run.log", "description_changes.log", "manual_review.log"):
        (log_dir / name).write_text("", encoding="utf-8")


def _collect_videos(service, video_id_filter: list[str], season_filter: list[int]) -> list[Video]:
    videos: list[Video] = []
    for v in list_my_full_game_videos(service):
        if video_id_filter and v.id not in video_id_filter:
            continue
        if season_filter and v.published_at.year not in season_filter:
            continue
        videos.append(v)
    return videos


def _gather_schedules(years: Iterable[int], refresh: bool, log_dir: Path) -> list[Game]:
    all_games: list[Game] = []
    for year in sorted(set(years)):
        try:
            all_games.extend(get_schedule(year, SCHEDULE_CACHE_DIR, refresh=refresh))
        except SeasonNotAvailableError as e:
            with (log_dir / "manual_review.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"reason": "scrape_failed", "season": year, "details": str(e)}) + "\n")
            print(f"WARN: could not load schedule for {year}: {e}", file=sys.stderr)
    return all_games


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize PUL YouTube full-game titles and descriptions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="(default) preview changes, no writes")
    mode.add_argument("--apply", action="store_true", help="push changes to YouTube after confirmation")
    parser.add_argument("--season", type=int, action="append", default=[], help="restrict to season(s)")
    parser.add_argument("--video-id", action="append", default=[], help="restrict to video ID(s)")
    parser.add_argument("--refresh-schedule", action="store_true", help="re-scrape stats hub")
    parser.add_argument("--skip-unchanged", action="store_true", help="(with --apply) skip videos where computed title/desc match current")
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR_DEFAULT)
    args = parser.parse_args(argv)

    if args.apply:
        args.dry_run = False

    log_dir: Path = args.log_dir
    _ensure_clean_log_dir(log_dir)

    abbrev = load_abbreviations(TEAM_ABBREVIATIONS_PATH)
    team_index = load_team_index(json.loads(TEAM_ABBREVIATIONS_PATH.read_text(encoding="utf-8")))
    template = DESCRIPTION_TEMPLATE_PATH.read_text(encoding="utf-8")

    creds = get_credentials()
    service = build_service(creds)

    print("Fetching video list...")
    videos = _collect_videos(service, args.video_id, args.season)
    print(f"Found {len(videos)} full-game video(s).")

    years_needed = {v.published_at.year for v in videos}
    print(f"Loading schedules for years: {sorted(years_needed)}")
    games = _gather_schedules(years_needed, args.refresh_schedule, log_dir)

    planned: list[tuple[Video, str, str]] = []  # (video, new_title, new_description)
    counts = defaultdict(int)

    for video in videos:
        teams = parse_teams(video.title, team_index)
        if teams is None:
            _log_manual_review(log_dir, video=video, reason="no_teams_parsed")
            counts["no_teams_parsed"] += 1
            continue
        result = match_video_to_game(video, teams, games)
        if isinstance(result, NoMatch):
            _log_manual_review(log_dir, video=video, reason="no_match", details=result.reason)
            counts["no_match"] += 1
            continue
        if isinstance(result, AmbiguousMatch):
            details = ", ".join(f"{g.season}-W{g.week} {g.date}" for g in result.candidates)
            _log_manual_review(log_dir, video=video, reason="ambiguous_match", details=details)
            counts["ambiguous_match"] += 1
            continue
        assert isinstance(result, Matched)

        new_title = build_new_title(result.game, abbrev)
        new_description = build_new_description(result.game, abbrev, template)

        if result.game.venue is None:
            _log_manual_review(log_dir, video=video, reason="missing_venue",
                               details=f"{result.game.season}-W{result.game.week} {result.game.date}")
            counts["missing_venue"] += 1

        _log_dry_run(log_dir, video=video, new_title=new_title)
        _log_description_change(log_dir, video=video, new_description=new_description)
        planned.append((video, new_title, new_description))
        counts["planned"] += 1

    print()
    print("Summary:")
    for key, val in sorted(counts.items()):
        print(f"  {key}: {val}")

    if args.dry_run:
        print()
        print(f"Dry run complete. See {log_dir}/ for full output.")
        return 0

    # --apply path: confirm
    print()
    print(f"About to update {counts['planned']} videos on YouTube.")
    print(f"  - {counts['planned']} title changes")
    print(f"  - {counts['planned']} description changes")
    if counts["missing_venue"]:
        print(f"  - {counts['missing_venue']} videos flagged for manual review (still pushed with best-effort content)")
    answer = input("Proceed? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. No videos updated.")
        return 1

    pushed = 0
    skipped = 0
    for video, new_title, new_description in planned:
        if args.skip_unchanged and new_title == video.title and new_description == video.description:
            skipped += 1
            continue
        try:
            update_video(service, video.id, new_title, new_description)
            pushed += 1
            print(f"  pushed: {video.id}")
        except Exception as e:
            _log_manual_review(log_dir, video=video, reason="api_error", details=str(e))
            print(f"  ERROR {video.id}: {e}", file=sys.stderr)

    print()
    print(f"Done. Pushed: {pushed}. Skipped (unchanged): {skipped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```powershell
git add src/cli.py
git commit -m "feat: CLI orchestrating dry-run preview and apply"
```

---

## Task 9: End-to-end smoke test

**Files:** none new — manual verification only.

- [ ] **Step 1: Run dry-run against a single known video**

Pick one video ID from the channel you know is a full game (a YouTube URL like `https://www.youtube.com/watch?v=XXXX` — the part after `v=` is the ID). Then:

```powershell
python -m src.cli --dry-run --video-id XXXX
```

Expected output:
- OAuth prompt opens (first run only).
- Stats hub schedule fetched for the video's season.
- Console prints `[OLD TITLE] -> [NEW TITLE]`.
- `logs/dry_run.log`, `logs/description_changes.log`, `logs/manual_review.log` are created.

- [ ] **Step 2: Inspect the logs**

```powershell
Get-Content logs\dry_run.log
Get-Content logs\description_changes.log
Get-Content logs\manual_review.log
```

Verify:
- `dry_run.log` has one line per video with the new title.
- `description_changes.log` shows the old description and the new template-rendered description.
- `manual_review.log` is empty if the video matched cleanly; otherwise inspect the entry.

- [ ] **Step 3: If anything looks wrong, fix and re-run before applying**

Common issues:
- Team parser misses a team → add an alias to `team_abbreviations.json` and re-run.
- No schedule match → check the stats hub URL pattern / scraper selectors.
- Description placeholders not replaced → check `description_template.txt` placeholder names.

- [ ] **Step 4: Run full dry-run on all videos**

```powershell
python -m src.cli --dry-run
```

Review `manual_review.log`. Decide whether to:
- Fix scraper / parser issues and re-run, or
- Accept the manual-review backlog and proceed to `--apply` for the videos that did match.

- [ ] **Step 5: Apply (when ready)**

```powershell
python -m src.cli --apply
```

Type `y` at the confirmation prompt. Verify a handful of updated videos in the YouTube Studio UI before assuming all 300 are correct.

- [ ] **Step 6: Final commit (if any tweaks were made during smoke test)**

```powershell
git add -A
git commit -m "chore: smoke test fixes"
```

---

## Self-review notes

- **Spec coverage**: every section of the spec maps to a task — auth (T6), youtube_client (T7), stats_hub_scraper (T4), title_parser (T3), normalizer (T5), cli (T8), config files (T2), logging schema (T8), confirmation prompt (T8), idempotency / `--skip-unchanged` (T8), team home locations constant (T4).
- **Placeholders**: the only deliberate "fill in based on actual HTML" content is in Task 4 step 5 — this is unavoidable because the HTML structure can't be known until the fixture is captured. Every other step has concrete code.
- **Open issues from spec**: the stats hub URL pattern and past-game venue exposure are addressed in Task 4 steps 1 and 5 (manual investigation moment). Doubleheader ambiguity is covered by `AmbiguousMatch` handling in Task 5. Neutral-site games surface via `manual_review.log` per Task 8.
- **Type consistency**: `Video` is defined in `normalizer.py` and imported by `youtube_client.py` and `cli.py`. `Game` is defined in `stats_hub_scraper.py` and imported everywhere else. No name drift.
