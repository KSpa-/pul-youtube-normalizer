# PUL YouTube Normalizer — Design

## Purpose

A Python tool that normalizes titles and descriptions of full-game videos on the PUL YouTube channel to a consistent format, using the PUL Stats Hub as the authoritative source for schedule data.

## Scope

In scope:
- Full-game videos only (`contentDetails.duration > PT1H`).
- All PUL seasons present on the stats hub: 2026, 2025, 2024, 2023, 2022, 2019.
- Title and description rewriting.
- Dry-run preview before any write, with `[OLD] -> [NEW]` log output.
- Manual-review log file for videos that can't be matched or have missing fields.

Out of scope (not built):
- Highlight/clip videos under one hour.
- Thumbnails, tags, playlists, scheduled visibility changes.
- Reverting changes (no rollback file beyond what YouTube's revision history provides).
- A web UI. CLI only.

## Target Output Formats

**Title:** `PUL {SeasonYear} W{WeekNumber}: {AwayShort} @ {HomeShort} - {M}/{D}`

Example: `PUL 2024 W3: Indy Red @ Nashville Shade - 4/15`

**Description:**

```
{Month Day, Year}
Week {WeekNumber} of the {SeasonYear} PUL season. Watch the {AwayFull} take on the {HomeFull} in {City}, {State} at the {StadiumName}.


About the PUL:

The Premier Ultimate League (PUL), founded in 2019, is the professional ultimate league for women and gender-expansive athletes that operates as a 501c6 nonprofit. Since the PUL's founding, the league and its teams actively strive to create an inclusive and competitive league showcasing athleticism and the game's spirit. The PUL has 10 member teams: Atlanta Soul, Austin Torch, DC Shadow, Indianapolis Red, Milwaukee Monarchs, Minnesota Strike, Nashville Nightshade, New York Gridlock, Philadelphia Surge, and Raleigh Radiance. These 10 teams compete in regular season play from April to June, with the championship taking place in June. In addition to all 10 teams highlighting athleticism and ultimate at its highest peak of competition, the PUL strives for gender, racial, and economic diversity.

The {SeasonYear} season schedule and stats can be found here: https://pul-stats-hub.pages.dev/

The PUL can be followed on social media at @premierultimateleague on Facebook, Instagram, LinkedIn, and YouTube.

Like us on Facebook:  https://www.facebook.com/premierultimateleague
Follow us on Instagram:  https://www.instagram.com/premierultimateleague
Shop for PUL Gear: https://teams.breakmark.com/group/pul
```

The boilerplate "About the PUL" block lives in `description_template.txt`. The first line and the season-year reference are filled per-video.

## Architecture (Approach B — modular package)

```
youtube_normalization_project/
├── client_secrets.json         (user-supplied; existing file, see "Open issue" below)
├── token.json                  (generated on first OAuth)
├── team_abbreviations.json     (seeded; user-editable)
├── description_template.txt    (boilerplate block)
├── schedule_cache/             (gitignored; populated by stats_hub_scraper)
│   ├── 2019.json
│   ├── 2022.json
│   ├── ... etc
├── logs/
│   ├── dry_run.log             (every old→new pair, run-stamped)
│   ├── description_changes.log (full description diffs)
│   └── manual_review.log       (unmatched / ambiguous / missing-field videos)
├── src/
│   ├── auth.py
│   ├── youtube_client.py
│   ├── stats_hub_scraper.py
│   ├── title_parser.py
│   ├── normalizer.py
│   └── cli.py
└── tests/
    ├── test_title_parser.py
    ├── test_normalizer.py
    └── test_stats_hub_scraper.py    (uses recorded HTML fixtures)
```

### Module responsibilities

**`auth.py`** — OAuth2 flow.
- Loads `client_secrets.json` (or the existing `client_secrets.json.json` — see Open Issues).
- On first run: opens browser via `InstalledAppFlow`, writes `token.json`.
- On later runs: refreshes from `token.json`.
- Scope: `https://www.googleapis.com/auth/youtube` (write needed for `videos.update`).
- Exposes one function: `get_credentials() -> google.oauth2.credentials.Credentials`.

**`youtube_client.py`** — Thin wrapper around `googleapiclient.discovery.build("youtube", "v3", ...)`.
- `list_my_full_game_videos()` — yields `{id, title, description, publishedAt, duration}` for every video on the authenticated user's `uploads` playlist where `duration > 1 hour`. Internally:
  - `channels.list(mine=true, part=contentDetails)` → uploads playlist ID.
  - Paginates `playlistItems.list` to get all video IDs (cost: 1 unit/page, 50 ids/page).
  - Batches into `videos.list(part="snippet,contentDetails", id=...)` (50 at a time) to get duration and full snippet.
  - Filters in-memory to duration > PT1H.
- `update_video(video_id, new_title, new_description)` — calls `videos.update` with `part="snippet"`. Cost: 50 units/call.
- All API calls go through a single retry-with-backoff helper for 5xx / 429 responses.

**`stats_hub_scraper.py`** — HTML scraper for `pul-stats-hub.pages.dev`.
- `get_schedule(season: int) -> list[Game]` where `Game` is a dataclass:
  ```python
  @dataclass
  class Game:
      season: int
      week: int                # integer parsed from "Week One" → 1
      date: datetime.date
      away_team: str           # canonical full name e.g. "Indianapolis Red"
      home_team: str
      venue: str | None        # e.g. "West High School"; None if hub doesn't list it
      city: str                # derived from home_team via TEAM_HOME_LOCATIONS (see below)
      state: str               # derived from home_team via TEAM_HOME_LOCATIONS (see below)
  ```
- Caches scraped seasons to `schedule_cache/{season}.json`. Loads from cache if present; pass `--refresh-schedule` on the CLI to force re-scrape.
- Owns a `TEAM_HOME_LOCATIONS` constant mapping each canonical team full name to its home `(city, state)`. The stats hub does not expose city/state per game, so these are derived from `home_team`. Seeded values:
  - Atlanta Soul → (Atlanta, GA)
  - Austin Torch → (Austin, TX)
  - DC Shadow → (Washington, DC)
  - Indianapolis Red → (Indianapolis, IN)
  - Milwaukee Monarchs → (Milwaukee, WI)
  - Minnesota Strike → (Minneapolis, MN)
  - Nashville Nightshade → (Nashville, TN)
  - New York Gridlock → (New York, NY)
  - Philadelphia Surge → (Philadelphia, PA)
  - Raleigh Radiance → (Raleigh, NC)
- Known limitation: neutral-site playoff/championship games will render with the home team's home city, which may be wrong. Flagged as an open issue (see below) and surfaced for any video where the scraped `venue` does not match the home team's expected venue patterns — though "expected venue" detection is out of scope for v1; user resolves manually via `manual_review.log` if needed.
- Uses `requests` + `BeautifulSoup`. Each season's schedule URL pattern is determined empirically on first run (suspect: `?season=YYYY`); the scraper logs the URL it used.
- Defensive: if a season URL returns 404 or 0 games, raises `SeasonNotAvailableError` and the CLI logs it to `manual_review.log` but continues with other seasons.
- Week strings ("Week One", "Week Two", ...) are mapped to integers via a small `WEEK_WORDS` dict; falls back to `int(re.search(r"\d+", s))` if a numeric form appears.

**`title_parser.py`** — Extracts team names from current (messy) titles.
- `parse_teams(title: str, known_team_names: list[str]) -> tuple[str, str] | None`
- Strategy: case-insensitive substring search for each canonical team name (and a small set of common typos/aliases per team — defined in `team_abbreviations.json` under an `aliases` key). Returns the two team names in the order they appear in the title.
- Does **not** try to identify home/away from the title — the stats hub is authoritative for that.
- Does **not** extract date or week from the title — `publishedAt` + stats hub provide those.

**`normalizer.py`** — Pure functions, no I/O.
- `match_video_to_game(video, season_games) -> Game | MatchResult` — given a video (publishedAt date + parsed team pair) and the full list of games across all seasons, returns the unique matching `Game` or one of: `NoMatch`, `AmbiguousMatch(candidates)`.
  - Match key: unordered team-pair equality AND `abs(publishedAt.date() - game.date) <= 7 days`.
  - If multiple games match within the 7-day window with the same team pair (unlikely but possible for doubleheaders/playoffs), returns `AmbiguousMatch`.
- `build_new_title(game, abbreviations) -> str`
- `build_new_description(game, template) -> str` — if `venue` is `None` (stadium not scraped), the location sentence is replaced with `"Watch the {AwayFull} take on the {HomeFull} in {City}, {State}."` (no stadium phrase) and the video is added to `manual_review.log` with `reason=missing_venue` so the user can fill in the stadium later. `city`/`state` are always present because they're derived from the home team.

**`cli.py`** — argparse entry point.
- Flags:
  - `--dry-run` (default `True`) — print/log changes, don't write.
  - `--apply` — write to YouTube. Before pushing, prints a summary like:
    ```
    About to update 87 videos on YouTube.
      - 87 title changes
      - 87 description changes
      - 12 videos flagged for manual review (still pushed with best-effort content)
    Proceed? [y/N]:
    ```
    Only `y` (case-insensitive) proceeds. Anything else aborts without writing.
  - `--season YYYY` (repeatable) — restrict to specific seasons. Default: all.
  - `--video-id ID` (repeatable) — restrict to specific videos (debugging).
  - `--refresh-schedule` — force re-scrape of the stats hub.
  - `--log-dir PATH` — override `./logs/`.
- Always writes the three log files regardless of dry-run vs apply mode. `--apply` adds a `pushed: true/false` marker per video.

## Data flow

```
1. auth.get_credentials()
2. youtube_client.list_my_full_game_videos()       -> [Video, ...]
3. for season in distinct(video.publishedAt.year for video in videos):
       stats_hub_scraper.get_schedule(season)        -> [Game, ...]
   all_games = flatten
4. for video in videos:
       teams = title_parser.parse_teams(video.title)
       if teams is None:
           log manual_review (reason="no teams parsed")
           continue
       match = normalizer.match_video_to_game(video, all_games)
       if match is NoMatch/AmbiguousMatch:
           log manual_review (reason="no_match" or "ambiguous_match")
           continue
       new_title = normalizer.build_new_title(match.game, abbreviations)
       new_description = normalizer.build_new_description(match.game, template)
       log dry_run: f"{video.id} | {video.title}  ->  {new_title}"
       log description_changes: full old vs new description
       if --apply:
           if user confirmed:
               youtube_client.update_video(...)
               mark pushed=true
```

## Idempotency

Running the script twice with `--apply` is safe but wasteful:
- The script does not compare new vs current YouTube metadata before pushing — it pushes the computed new title/description regardless.
- If the second run computes the same output (same schedule cache, same parser logic), each video gets re-written with identical content. No data loss; just spent quota.
- If you want to skip already-correct videos, pass `--skip-unchanged`, which fetches the current snippet and pushes only when new_title or new_description differ from current.

## Error handling

- **OAuth failures**: print friendly message with the underlying error, exit 1. No retry — user must rerun.
- **YouTube API 5xx / 429**: exponential backoff (1s, 2s, 4s, 8s, 16s, then fail). Per-call.
- **YouTube API 4xx (other than 429)**: log full error to `manual_review.log` for that video and continue.
- **Stats hub scrape fails for a season**: log to `manual_review.log`, continue with other seasons. Videos from that season will appear as `no_match` and surface in the same log.
- **Title parse misses team names**: log to `manual_review.log`. Don't crash.
- **Schedule has 0 games for a published season**: same as scrape fail. Surfaces in `manual_review.log`.

## Quota considerations

Per default 10,000-unit daily quota:
- Listing videos: ~6 `playlistItems.list` (1 unit) + ~6 `videos.list` (1 unit) = ~12 units.
- Each `videos.update`: 50 units.
- ~100 full games × 50 = 5,000 units. Comfortably under 10K/day even with retries.
- Reads to the stats hub are unmetered (different service).

## Testing

- `test_title_parser.py` — table of synthetic dirty titles → expected `(away, home)` tuple. Covers `@` vs `vs`, reversed order, casing, missing whitespace.
- `test_normalizer.py` — `build_new_title` / `build_new_description` snapshot tests with golden strings. Match logic tested against synthetic `Game` list (no I/O).
- `test_stats_hub_scraper.py` — saved HTML fixture for a 2024 schedule page, verify the parser produces expected `Game` records. Re-record fixture if site changes.
- No end-to-end YouTube test — would require live OAuth + a sacrificial channel. Manual smoke test on a single `--video-id` instead.

## Configuration files

**`team_abbreviations.json`** (seeded, user-editable):
```json
{
  "Atlanta Soul":         {"short": "Atlanta Soul",       "aliases": ["Soul", "ATL Soul"]},
  "Austin Torch":         {"short": "Austin Torch",       "aliases": ["Torch", "AUS Torch"]},
  "DC Shadow":            {"short": "DC Shadow",          "aliases": ["Shadow", "Washington Shadow"]},
  "Indianapolis Red":     {"short": "Indy Red",           "aliases": ["Indy Red", "Indianapolis"]},
  "Milwaukee Monarchs":   {"short": "Milwaukee Monarchs", "aliases": ["Monarchs", "MIL Monarchs"]},
  "Minnesota Strike":     {"short": "Minn Strike",        "aliases": ["Strike", "MN Strike"]},
  "Nashville Nightshade": {"short": "Nashville Shade",    "aliases": ["Nightshade", "Shade", "NSH Nightshade"]},
  "New York Gridlock":    {"short": "NY Gridlock",        "aliases": ["Gridlock", "NYC Gridlock"]},
  "Philadelphia Surge":   {"short": "Philly Surge",       "aliases": ["Surge", "Philly Surge", "Philadelphia"]},
  "Raleigh Radiance":     {"short": "Raleigh Radiance",   "aliases": ["Radiance", "RAL Radiance"]}
}
```

**`description_template.txt`** — see "Target Output Formats" above. The line containing `{LOCATION_SENTENCE}` is the only line that's conditionally rewritten when venue data is missing.

## Manual review log format

One JSON object per line (jsonl), for easy grep/parse:

```json
{"video_id": "abc123", "title": "...", "publishedAt": "2024-04-15T...", "reason": "no_match | ambiguous_match | no_teams_parsed | missing_venue | scrape_failed | api_error", "details": "free text"}
```

## Open issues / decisions to verify during implementation

1. **`client_secrets.json` filename**: the file currently in the project is `client_secrets.json.json` (double extension). The script should look for both names and warn if it finds the double-extension form, suggesting a rename.
2. **Stats hub URL pattern**: WebFetch couldn't confirm whether per-season URLs are `?season=YYYY` or `/season/YYYY/` or a JS-rendered dropdown. First implementation step is to confirm this manually and codify in the scraper.
3. **Past-game venue exposure**: WebFetch hinted past games may not show venue in the rendered HTML. If true at scrape time, every past-game video will hit `missing_venue` in `manual_review.log` until the stats hub adds it. The description falls back to no-location phrasing — script still ships titles correctly.
4. **Doubleheader / playoff ambiguity**: if two games match the same team pair within 7 days, the match is flagged ambiguous and skipped. May need to narrow the window or add a manual override CSV if this is common.
5. **Neutral-site games**: playoffs/championships may be hosted at a neutral venue. The script renders city/state from the home team's home location, which will be wrong in those cases. The user can spot these via the venue mismatch in `manual_review.log` (when implemented) or by reviewing the dry-run output for known playoff weeks. Out of scope for v1 to auto-correct.

## Follow-ups (deferred, expected manual work)

Owner confirmed that some location data will need manual cleanup after the first run. To make that easier:

- The dry-run output and `manual_review.log` together act as the worklist. After the first full dry-run, the owner walks the log and writes correct city/state/venue back into either `TEAM_HOME_LOCATIONS` (for permanent corrections) or a future `venue_overrides.csv` (for one-off games like playoffs).
- A `venue_overrides.csv` is **not** built in v1, but the design leaves a clean seam for it: `stats_hub_scraper.get_schedule()` returns the canonical `Game` list, and a future override layer can patch `venue/city/state` on matching rows before they reach the normalizer.
- After the first full apply, expect a second pass: re-run dry-run, address remaining manual-review entries, then `--apply --skip-unchanged` to push only the corrections.
