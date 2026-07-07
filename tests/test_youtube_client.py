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


def test_parse_iso8601_duration_live_stream_p0d_returns_zero():
    # YouTube returns "P0D" for live and upcoming streams; must not crash listing.
    assert parse_iso8601_duration("P0D") == 0


def test_parse_iso8601_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_iso8601_duration("banana")
