import httplib2
import pytest
from googleapiclient.errors import HttpError

import pul_normalizer.youtube_client as youtube_client
from pul_normalizer.youtube_client import get_videos_by_ids, parse_iso8601_duration


def _http_error(status: int, headers: dict | None = None) -> HttpError:
    info = {"status": str(status)}
    if headers:
        info.update(headers)
    return HttpError(httplib2.Response(info), b"error")


def test_call_with_retry_honors_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(youtube_client.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429, {"retry-after": "7"})
        return "ok"

    assert youtube_client._call_with_retry(flaky) == "ok"
    # Retry-After (7s) wins over the smaller exponential delays (1s, 2s).
    assert sleeps == [7, 7]


def test_call_with_retry_raises_non_retryable_immediately(monkeypatch):
    monkeypatch.setattr(youtube_client.time, "sleep",
                        lambda s: pytest.fail("should not sleep on 403"))
    with pytest.raises(HttpError):
        youtube_client._call_with_retry(lambda: (_ for _ in ()).throw(_http_error(403)))


class _StubRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _StubVideosResource:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return _StubRequest(self._response)


class _StubService:
    def __init__(self, response):
        self.videos_resource = _StubVideosResource(response)

    def videos(self):
        return self.videos_resource


def test_get_videos_by_ids_parses_api_items():
    service = _StubService({
        "items": [
            {
                "id": "v1",
                "snippet": {"title": "Game", "description": "d",
                            "publishedAt": "2024-04-15T18:00:00Z"},
                "contentDetails": {"duration": "PT2H"},
            },
            {
                "id": "v2",
                "snippet": {"title": "Live now",
                            "publishedAt": "2024-04-16T18:00:00Z"},
                "contentDetails": {"duration": "P0D"},
            },
        ]
    })
    videos = list(get_videos_by_ids(service, ["v1", "v2"]))
    assert [v.id for v in videos] == ["v1", "v2"]
    assert videos[0].duration_seconds == 7200
    assert videos[0].published_at.year == 2024
    assert videos[1].duration_seconds == 0
    assert videos[1].description == ""
    assert service.videos_resource.calls[0]["id"] == "v1,v2"


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
