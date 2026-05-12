"""Command-line entry point for the PUL YouTube normalizer."""
from __future__ import annotations

import argparse
import json
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
    counts: dict[str, int] = defaultdict(int)

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
