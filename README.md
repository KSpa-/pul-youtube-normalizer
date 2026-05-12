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
