"""YouTube Data API v3 wrapper for listing/updating videos."""
from __future__ import annotations

import datetime
import re
import time
from typing import Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from .normalizer import Video


FULL_GAME_MIN_SECONDS = 3600  # > 1 hour
MAX_RETRIES = 5


def parse_iso8601_duration(s: str) -> int:
    """Parse YouTube's ISO 8601 duration like 'PT1H30M15S' to total seconds.

    Only handles H/M/S — YouTube videos don't use D/Y components in duration.
    Live and upcoming streams report "P0D"; treat those as 0 seconds so they
    fall below the full-game threshold instead of crashing the listing.
    """
    if s == "P0D":
        return 0
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
    """Run a `request.execute()`-style callable with exponential backoff on 5xx/429.

    Honors the Retry-After header when the server sends one larger than the
    current backoff delay.
    """
    delay = 1
    for attempt in range(MAX_RETRIES):
        try:
            return request_callable()
        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else 0
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                try:
                    retry_after = int(e.resp.get("retry-after", 0))
                except (TypeError, ValueError):
                    retry_after = 0  # ignore HTTP-date form
                time.sleep(max(delay, retry_after))
                delay *= 2
                continue
            raise


def build_service(creds: Credentials):
    """Build a YouTube Data API v3 service object from OAuth credentials."""
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _video_from_api_item(item: dict) -> Video:
    snippet = item["snippet"]
    return Video(
        id=item["id"],
        title=snippet["title"],
        description=snippet.get("description", ""),
        published_at=datetime.datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        ),
        duration_seconds=parse_iso8601_duration(item["contentDetails"]["duration"]),
    )


def get_videos_by_ids(service, video_ids: list[str]) -> Iterator[Video]:
    """Yield Video records for the given IDs (batched 50 per videos.list call).

    No duration filtering — callers decide. IDs the API doesn't return
    (deleted/private) are simply absent from the output.
    """
    for i in range(0, len(video_ids), 50):
        batch = list(video_ids[i : i + 50])
        resp = _call_with_retry(
            lambda: service.videos()
            .list(part="snippet,contentDetails", id=",".join(batch))
            .execute()
        )
        for item in resp.get("items", []):
            yield _video_from_api_item(item)


def list_full_game_videos(service, channel_handle: str | None = None) -> Iterator[Video]:
    """Yield every video on the target channel longer than 1 hour.

    If `channel_handle` is provided (e.g. "@premierultimateleague"), looks up
    that channel by handle — required for Brand Account channels, since they
    aren't returned by `channels.list(mine=True)`. Otherwise falls back to the
    authenticated user's own (personal) channel.
    """
    if channel_handle:
        handle = channel_handle if channel_handle.startswith("@") else f"@{channel_handle}"
        channels = _call_with_retry(
            lambda: service.channels().list(part="contentDetails", forHandle=handle).execute()
        )
    else:
        channels = _call_with_retry(
            lambda: service.channels().list(part="contentDetails", mine=True).execute()
        )
    items = channels.get("items", [])
    if not items:
        target = repr(channel_handle) if channel_handle else "the authenticated user"
        raise RuntimeError(f"No channel found for {target}.")
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

    # 3. Batch videos.list (50 ids per call) and keep the full-game ones.
    for video in get_videos_by_ids(service, video_ids):
        if video.duration_seconds >= FULL_GAME_MIN_SECONDS:
            yield video


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
