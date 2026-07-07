import datetime
import json

import pytest

import pul_normalizer.cli as cli
from pul_normalizer.cli import (
    _extract_video_id,
    _load_backup,
    _plan_videos,
    _rollback,
    _run_log_dir,
    _write_backup,
)
from pul_normalizer.normalizer import Abbreviations, Video
from pul_normalizer.stats_hub_scraper import Game
from pul_normalizer.title_parser import load_team_index


def _video(video_id="v1", title="Indy Red @ Nashville Shade 4/15/2024",
           published="2024-04-15T18:00:00+00:00") -> Video:
    return Video(
        id=video_id, title=title, description="old",
        published_at=datetime.datetime.fromisoformat(published),
        duration_seconds=4000,
    )


def _game(away="Indy Red", home="Nashville NightShade") -> Game:
    return Game(
        season=2024, week=3, date=datetime.date(2024, 4, 15),
        away_team=away, home_team=home, venue="West High School",
        location="Nashville, TN",
    )


@pytest.fixture
def team_index():
    raw = {
        "Indy Red": {"short": "Indy Red", "aliases": ["Indianapolis Red"]},
        "Nashville NightShade": {"short": "Nashville Shade", "aliases": ["Nashville Shade"]},
        "Atlanta Soul": {"short": "Atlanta Soul", "aliases": ["Soul"]},
    }
    return load_team_index(raw)


TEMPLATE = "{GAME_DATE_LINE} | {WEEK_PHRASE} | {LOCATION_SENTENCE} | {SEASON_YEAR}"


def test_plan_videos_happy_path(tmp_path, team_index):
    abbrev = Abbreviations(short_by_full={
        "Indy Red": "Indy Red", "Nashville NightShade": "Nashville Shade",
    })
    planned, counts = _plan_videos(
        [_video()], [_game()], team_index, abbrev, TEMPLATE, tmp_path,
    )
    assert len(planned) == 1
    assert counts["planned"] == 1
    video, new_title, new_description = planned[0]
    assert new_title == "PUL 2024 W3: Indy Red @ Nashville Shade - 4/15"


def test_plan_videos_isolates_per_video_errors(tmp_path, team_index):
    # Abbreviations missing "Nashville NightShade" -> KeyError while building
    # the title for v1. That must not abort the run: v2 (Soul game) still plans.
    abbrev = Abbreviations(short_by_full={
        "Indy Red": "Indy Red", "Atlanta Soul": "Atlanta Soul",
    })
    bad = _video(video_id="v1")
    good = _video(video_id="v2", title="Indy Red @ Atlanta Soul 4/20/2024")
    games = [
        _game(),
        Game(season=2024, week=4, date=datetime.date(2024, 4, 20),
             away_team="Indy Red", home_team="Atlanta Soul",
             venue=None, location="Atlanta, GA"),
    ]
    planned, counts = _plan_videos(
        [bad, good], games, team_index, abbrev, TEMPLATE, tmp_path,
    )
    assert counts["processing_error"] == 1
    assert counts["planned"] == 1
    assert [v.id for v, _, _ in planned] == ["v2"]
    # The failure is recorded for manual review with the video id.
    entries = [json.loads(line) for line in
               (tmp_path / "manual_review.log").read_text(encoding="utf-8").splitlines()]
    assert any(e["video_id"] == "v1" and e["reason"] == "processing_error"
               for e in entries)


def test_default_paths_are_anchored_to_project_root():
    # The CLI must work no matter what directory it is invoked from.
    assert cli.SCHEDULE_CACHE_DIR.is_absolute()
    assert cli.LOG_DIR_DEFAULT.is_absolute()
    assert cli.DESCRIPTION_TEMPLATE_PATH.is_absolute()
    assert cli.DESCRIPTION_TEMPLATE_PATH.exists()


def test_run_log_dir_is_timestamped_per_run(tmp_path):
    now = datetime.datetime(2026, 7, 6, 20, 45, 12)
    assert _run_log_dir(tmp_path, now) == tmp_path / "run_2026-07-06_20-45-12"


def test_backup_round_trip(tmp_path):
    planned = [
        (_video(video_id="v1"), "new title 1", "new desc 1"),
        (_video(video_id="v2"), "new title 2", "new desc 2"),
    ]
    path = tmp_path / "backup.json"
    _write_backup(path, planned, pushed_ids={"v2"})
    entries = _load_backup(path)
    assert [e["video_id"] for e in entries] == ["v1", "v2"]
    assert entries[0]["old_title"] == "Indy Red @ Nashville Shade 4/15/2024"
    assert entries[0]["old_description"] == "old"
    assert entries[0]["new_title"] == "new title 1"
    assert entries[0]["pushed"] is False
    assert entries[1]["pushed"] is True


def test_load_backup_accepts_run_directory(tmp_path):
    _write_backup(tmp_path / "backup.json", [(_video(), "t", "d")], pushed_ids=set())
    entries = _load_backup(tmp_path)  # directory, not file
    assert entries[0]["video_id"] == "v1"


def test_rollback_restores_only_pushed_entries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli, "update_video",
        lambda service, vid, title, desc: calls.append((vid, title, desc)),
    )
    entries = [
        {"video_id": "v1", "old_title": "old t1", "old_description": "old d1",
         "new_title": "n", "new_description": "n", "pushed": True},
        {"video_id": "v2", "old_title": "old t2", "old_description": "old d2",
         "new_title": "n", "new_description": "n", "pushed": False},
    ]
    restored, errors = _rollback(service=None, entries=entries)
    assert restored == 1
    assert errors == 0
    assert calls == [("v1", "old t1", "old d1")]


def test_rollback_counts_errors_and_continues(monkeypatch):
    def boom(service, vid, title, desc):
        if vid == "v1":
            raise RuntimeError("api down")

    monkeypatch.setattr(cli, "update_video", boom)
    entries = [
        {"video_id": "v1", "old_title": "t", "old_description": "d",
         "new_title": "n", "new_description": "n", "pushed": True},
        {"video_id": "v2", "old_title": "t", "old_description": "d",
         "new_title": "n", "new_description": "n", "pushed": True},
    ]
    restored, errors = _rollback(service=None, entries=entries)
    assert restored == 1
    assert errors == 1


def test_video_season_year_prefers_title_date():
    # Game from June 2024 uploaded in January 2025: season year is 2024.
    v = _video(title="Indy Red @ Nashville Shade 6/22/2024",
               published="2025-01-10T18:00:00+00:00")
    assert cli._video_season_year(v) == 2024


def test_video_season_year_falls_back_to_published_year():
    v = _video(title="Indy Red @ Nashville Shade",
               published="2025-01-10T18:00:00+00:00")
    assert cli._video_season_year(v) == 2025


def test_collect_videos_fetches_directly_when_ids_given(monkeypatch, capsys):
    # Explicit --video-id must not burn quota listing the whole channel.
    full_game = _video(video_id="v1")
    short_clip = _video(video_id="v2")
    short_clip.duration_seconds = 120
    monkeypatch.setattr(cli, "get_videos_by_ids",
                        lambda service, ids: iter([full_game, short_clip]))

    def full_listing_forbidden(*args, **kwargs):
        raise AssertionError("full channel listing should not run for explicit IDs")

    monkeypatch.setattr(cli, "list_full_game_videos", full_listing_forbidden)

    vids = cli._collect_videos(None, ["v1", "v2", "vmissing"], [], None)
    assert [v.id for v in vids] == ["v1"]
    # Videos that were requested but dropped (too short / not found) are reported.
    err = capsys.readouterr().err
    assert "v2" in err
    assert "vmissing" in err


def test_collect_videos_season_filter_uses_title_date_year(monkeypatch):
    late_upload = _video(video_id="v1", title="Indy Red @ Nashville Shade 6/22/2024",
                         published="2025-01-10T18:00:00+00:00")
    next_season = _video(video_id="v2", title="Indy Red @ Nashville Shade 5/1/2025",
                         published="2025-05-02T18:00:00+00:00")
    monkeypatch.setattr(
        cli, "list_full_game_videos",
        lambda service, channel_handle=None: iter([late_upload, next_season]),
    )
    vids = cli._collect_videos(None, [], [2024], None)
    assert [v.id for v in vids] == ["v1"]


def test_split_unchanged_partitions_planned_videos():
    changed = (_video(video_id="v1"), "new title", "new desc")
    unchanged_video = _video(video_id="v2", title="already normalized")
    unchanged_video.description = "already normalized desc"
    unchanged = (unchanged_video, "already normalized", "already normalized desc")

    to_push, skipped = cli._split_unchanged([changed, unchanged], skip_unchanged=True)
    assert [v.id for v, _, _ in to_push] == ["v1"]
    assert skipped == 1

    to_push, skipped = cli._split_unchanged([changed, unchanged], skip_unchanged=False)
    assert len(to_push) == 2
    assert skipped == 0


def test_gather_schedules_survives_network_errors(tmp_path, monkeypatch):
    import requests

    def boom(year, cache_dir, refresh=False):
        raise requests.ConnectionError("dns fail")

    monkeypatch.setattr(cli, "get_schedule", boom)
    games = cli._gather_schedules([2024], refresh=False, log_dir=tmp_path)
    assert games == []
    log = (tmp_path / "manual_review.log").read_text(encoding="utf-8")
    assert "scrape_failed" in log


@pytest.mark.parametrize("s,expected", [
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_extract_video_id(s, expected):
    assert _extract_video_id(s) == expected


@pytest.mark.parametrize("s", [
    "https://www.youtube.com/playlist?list=PLxyz",  # no video id present
    "https://youtube.com/",                         # bare host
    "https://example.com/watch?v=dQw4w9WgXcQ",      # not a YouTube URL
])
def test_extract_video_id_rejects_unrecognizable_urls(s):
    with pytest.raises(ValueError):
        _extract_video_id(s)


def test_main_exits_cleanly_on_bad_video_id_url(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--video-id", "https://www.youtube.com/playlist?list=PLxyz"])
    assert exc.value.code == 2
    assert "video-id" in capsys.readouterr().err
