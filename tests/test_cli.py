import datetime
import json

import pytest

import cli
from cli import (
    _extract_video_id,
    _load_backup,
    _plan_videos,
    _rollback,
    _run_log_dir,
    _write_backup,
)
from normalizer import Abbreviations, Video
from stats_hub_scraper import Game
from title_parser import load_team_index


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


@pytest.mark.parametrize("s,expected", [
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_extract_video_id(s, expected):
    assert _extract_video_id(s) == expected
