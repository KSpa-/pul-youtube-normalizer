"""Command-line entry point for the PUL YouTube normalizer."""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import requests

from .auth import get_credentials
from .normalizer import (
    AmbiguousMatch,
    Matched,
    NoMatch,
    Video,
    abbreviations_from_teams,
    build_new_description,
    build_new_title,
    match_video_to_game,
)
from .stats_hub_scraper import (
    Game,
    SeasonNotAvailableError,
    get_schedule,
)
from .team_registry import PROJECT_ROOT, load_teams
from .title_parser import load_team_index, parse_date_from_title, parse_teams
from .youtube_client import (
    FULL_GAME_MIN_SECONDS,
    build_service,
    get_videos_by_ids,
    list_full_game_videos,
    update_video,
)


SCHEDULE_CACHE_DIR = PROJECT_ROOT / "schedule_cache"
LOG_DIR_DEFAULT = PROJECT_ROOT / "logs"
DESCRIPTION_TEMPLATE_PATH = PROJECT_ROOT / "description_template.txt"
DEFAULT_CHANNEL_HANDLE = "@premierultimateleague"


def _extract_video_id(s: str) -> str:
    """Return the bare YouTube video ID from either a URL or an already-bare ID.

    Accepts https://youtu.be/<id>, https://www.youtube.com/watch?v=<id>, and
    plain `<id>` strings. Raises ValueError for any URL a video ID cannot be
    extracted from — silently passing it through would just produce a
    mystifying "Found 0 videos" later.
    """
    if "youtu.be/" in s or "youtube.com/" in s:
        u = urlparse(s)
        if u.netloc.endswith("youtu.be"):
            vid = u.path.lstrip("/").split("/")[0]
            if vid:
                return vid
        if "youtube.com" in u.netloc:
            qs = parse_qs(u.query)
            if "v" in qs:
                return qs["v"][0]
            # /shorts/<id> or /embed/<id> fallback
            parts = [p for p in u.path.split("/") if p]
            if parts and parts[0] in ("shorts", "embed", "live") and len(parts) > 1:
                return parts[1]
        raise ValueError(f"Cannot extract a video ID from URL: {s!r}")
    if "://" in s:
        raise ValueError(f"Not a YouTube URL: {s!r}")
    return s


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


def _run_log_dir(base: Path, now: datetime.datetime) -> Path:
    """Each invocation logs into its own timestamped directory so a later run
    never truncates the backup/audit trail of an earlier one."""
    return base / now.strftime("run_%Y-%m-%d_%H-%M-%S")


def _write_backup(path: Path, planned: list[tuple[Video, str, str]],
                  pushed_ids: set[str] = frozenset()) -> None:
    """Write a machine-readable record of old and new title/description per video.

    This is the rollback source of truth: `pushed` marks entries actually
    written to YouTube (only those are restored by --rollback).
    """
    entries = [
        {
            "video_id": video.id,
            "old_title": video.title,
            "old_description": video.description,
            "new_title": new_title,
            "new_description": new_description,
            "pushed": video.id in pushed_ids,
        }
        for video, new_title, new_description in planned
    ]
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_backup(path: Path) -> list[dict]:
    """Load a backup file; accepts either the backup.json or its run directory."""
    p = Path(path)
    if p.is_dir():
        p = p / "backup.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _rollback(service, entries: list[dict]) -> tuple[int, int]:
    """Restore old title/description for every pushed entry. Returns (restored, errors)."""
    restored = 0
    errors = 0
    for e in entries:
        if not e.get("pushed"):
            continue
        try:
            update_video(service, e["video_id"], e["old_title"], e["old_description"])
            restored += 1
            print(f"  restored: {e['video_id']}")
        except Exception as ex:
            errors += 1
            print(f"  ERROR {e['video_id']}: {ex}", file=sys.stderr)
    return restored, errors


def _video_season_year(video: Video) -> int:
    """Best guess at the season a video belongs to.

    Prefer the date embedded in the title — a June 2024 game uploaded in
    January 2025 belongs to the 2024 season, not 2025. Fall back to the
    upload year when the title has no date.
    """
    title_date = parse_date_from_title(video.title)
    if title_date is not None:
        return title_date.year
    return video.published_at.year


def _collect_videos(service, video_id_filter: list[str], season_filter: list[int],
                    channel_handle: str | None) -> list[Video]:
    if video_id_filter:
        # Explicit IDs: fetch directly instead of paging the whole channel.
        candidates = [
            v for v in get_videos_by_ids(service, video_id_filter)
            if v.duration_seconds >= FULL_GAME_MIN_SECONDS
        ]
        dropped = set(video_id_filter) - {v.id for v in candidates}
        for vid in sorted(dropped):
            print(f"WARN: requested video {vid} not found or shorter than "
                  f"{FULL_GAME_MIN_SECONDS // 3600}h; skipping.", file=sys.stderr)
    else:
        candidates = list_full_game_videos(service, channel_handle=channel_handle)

    return [
        v for v in candidates
        if not season_filter or _video_season_year(v) in season_filter
    ]


def _gather_schedules(years: Iterable[int], refresh: bool, log_dir: Path) -> list[Game]:
    all_games: list[Game] = []
    for year in sorted(set(years)):
        try:
            all_games.extend(get_schedule(year, SCHEDULE_CACHE_DIR, refresh=refresh))
        except (SeasonNotAvailableError, requests.RequestException) as e:
            with (log_dir / "manual_review.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"reason": "scrape_failed", "season": year, "details": str(e)}) + "\n")
            print(f"WARN: could not load schedule for {year}: {e}", file=sys.stderr)
    return all_games


def _plan_videos(
    videos: list[Video],
    games: list[Game],
    team_index,
    abbrev,
    template: str,
    log_dir: Path,
) -> tuple[list[tuple[Video, str, str]], dict[str, int]]:
    """Match each video to a game and build its new title/description.

    A failure while processing one video is logged as `processing_error` and
    must never abort the rest of the run.
    """
    planned: list[tuple[Video, str, str]] = []
    counts: dict[str, int] = defaultdict(int)

    for video in videos:
        try:
            teams = parse_teams(video.title, team_index)
            if teams is None:
                _log_manual_review(log_dir, video=video, reason="no_teams_parsed")
                counts["no_teams_parsed"] += 1
                continue
            # Prefer date embedded in the title (more accurate than publishedAt,
            # which lags by upload/edit time). Use a tight ±2-day window when we
            # have a title date; widen to ±14 days for publishedAt fallback.
            title_date = parse_date_from_title(video.title)
            if title_date is not None:
                result = match_video_to_game(video, teams, games, match_date=title_date, window_days=2)
            else:
                result = match_video_to_game(video, teams, games, window_days=14)
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
        except Exception as e:
            _log_manual_review(log_dir, video=video, reason="processing_error", details=repr(e))
            counts["processing_error"] += 1
            print(f"WARN: error processing {video.id} ({video.title!r}): {e}", file=sys.stderr)

    return planned, counts


def _split_unchanged(
    planned: list[tuple[Video, str, str]], skip_unchanged: bool
) -> tuple[list[tuple[Video, str, str]], int]:
    """Partition planned changes into (to_push, skipped_count).

    With skip_unchanged, videos whose computed title and description already
    match the current ones are dropped — before the confirmation prompt, so
    the number the user confirms is the number actually pushed.
    """
    if not skip_unchanged:
        return list(planned), 0
    to_push = [
        (video, new_title, new_description)
        for video, new_title, new_description in planned
        if not (new_title == video.title and new_description == video.description)
    ]
    return to_push, len(planned) - len(to_push)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pul-normalizer",
        description="Normalize PUL YouTube full-game titles and descriptions.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="(default) preview changes, no writes")
    mode.add_argument("--apply", action="store_true", help="push changes to YouTube after confirmation")
    parser.add_argument("--season", type=int, action="append", default=[], help="restrict to season(s)")
    parser.add_argument("--video-id", action="append", default=[],
                        help="restrict to video ID(s); accepts bare IDs or YouTube URLs")
    parser.add_argument("--refresh-schedule", action="store_true", help="re-scrape stats hub")
    parser.add_argument("--skip-unchanged", action="store_true", help="(with --apply) skip videos where computed title/desc match current")
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR_DEFAULT,
                        help="base directory for per-run log folders")
    parser.add_argument("--channel-handle", default=DEFAULT_CHANNEL_HANDLE,
                        help=f"YouTube handle of the channel to operate on (default: {DEFAULT_CHANNEL_HANDLE})")
    parser.add_argument("--rollback", type=Path, metavar="RUN_DIR_OR_BACKUP_JSON",
                        help="restore old titles/descriptions from a previous run's backup.json")
    args = parser.parse_args(argv)

    if args.apply:
        args.dry_run = False

    if args.rollback:
        entries = _load_backup(args.rollback)
        pushed = [e for e in entries if e.get("pushed")]
        if not pushed:
            print("Nothing to roll back: no pushed entries in that backup.")
            return 0
        print(f"About to restore old title/description for {len(pushed)} video(s):")
        for e in pushed:
            print(f"  {e['video_id']}: {e['new_title']!r} -> {e['old_title']!r}")
        answer = input("Proceed? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted. No videos restored.")
            return 1
        service = build_service(get_credentials())
        restored, errors = _rollback(service, entries)
        print(f"Done. Restored: {restored}. Errors: {errors}.")
        return 0 if errors == 0 else 1

    # Normalize --video-id values: accept bare IDs or YouTube URLs.
    try:
        args.video_id = [_extract_video_id(v) for v in args.video_id]
    except ValueError as e:
        parser.error(f"--video-id: {e}")

    log_dir = _run_log_dir(args.log_dir, datetime.datetime.now())
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Logging this run to {log_dir}\\")

    teams_raw = load_teams()
    abbrev = abbreviations_from_teams(teams_raw)
    team_index = load_team_index(teams_raw)
    template = DESCRIPTION_TEMPLATE_PATH.read_text(encoding="utf-8")

    creds = get_credentials()
    service = build_service(creds)

    print(f"Fetching video list for {args.channel_handle}...")
    videos = _collect_videos(service, args.video_id, args.season, args.channel_handle)
    print(f"Found {len(videos)} full-game video(s).")

    years_needed = {_video_season_year(v) for v in videos}
    print(f"Loading schedules for years: {sorted(years_needed)}")
    games = _gather_schedules(years_needed, args.refresh_schedule, log_dir)

    planned, counts = _plan_videos(videos, games, team_index, abbrev, template, log_dir)

    print()
    print("Summary:")
    for key, val in sorted(counts.items()):
        print(f"  {key}: {val}")

    if args.dry_run:
        print()
        print(f"Dry run complete. See {log_dir}/ for full output.")
        return 0

    # --apply path: confirm
    to_push, skipped = _split_unchanged(planned, args.skip_unchanged)
    print()
    if skipped:
        print(f"Skipping {skipped} unchanged video(s).")
    if not to_push:
        print("Nothing to push.")
        return 0
    print(f"About to update {len(to_push)} videos on YouTube (title + description).")
    if counts["missing_venue"]:
        print(f"  - {counts['missing_venue']} videos flagged for manual review (still pushed with best-effort content)")
    answer = input("Proceed? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted. No videos updated.")
        return 1

    # Write the rollback backup BEFORE touching YouTube, then re-write it with
    # pushed flags as we go so a crash mid-run still leaves an accurate record.
    backup_path = log_dir / "backup.json"
    _write_backup(backup_path, to_push)

    pushed_ids: set[str] = set()
    for video, new_title, new_description in to_push:
        try:
            update_video(service, video.id, new_title, new_description)
            pushed_ids.add(video.id)
            _write_backup(backup_path, to_push, pushed_ids)
            print(f"  pushed: {video.id}")
        except Exception as e:
            _log_manual_review(log_dir, video=video, reason="api_error", details=str(e))
            print(f"  ERROR {video.id}: {e}", file=sys.stderr)

    print()
    print(f"Done. Pushed: {len(pushed_ids)}. Skipped (unchanged): {skipped}.")
    print(f"Rollback available: python -m pul_normalizer --rollback {backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
