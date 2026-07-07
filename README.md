# PUL YouTube Normalizer

Normalizes titles and descriptions of full-game videos on the PUL YouTube channel.

## Setup

1. Place your OAuth client secrets JSON at `client_secrets.json` (download from Google Cloud Console).
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (mac/linux).
3. `pip install -e ".[dev]"`.

## Usage

Dry-run (default — no writes):
```
python -m pul_normalizer --dry-run
```

Apply changes (requires interactive `y/N` confirmation):
```
python -m pul_normalizer --apply
```

(After `pip install -e .` the `pul-normalizer` command works as a shorthand
for `python -m pul_normalizer`.)

Each run writes its logs to a timestamped folder under `logs/` (e.g.
`logs/run_2026-07-06_20-45-12/`). An `--apply` run also writes `backup.json`
there — the old and new title/description for every video, with a `pushed`
flag — before anything is sent to YouTube.

Undo an apply run:
```
python -m pul_normalizer --rollback logs/run_2026-07-06_20-45-12
```

Team data (canonical names, locations, short forms, aliases, Stats Hub
spellings) lives in `data/teams_info.json` — the single source of truth.

Run tests with `pytest`.

See `docs/superpowers/specs/2026-05-12-pul-youtube-normalizer-design.md` for full design.
