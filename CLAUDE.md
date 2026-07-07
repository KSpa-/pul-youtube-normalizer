# PUL YouTube Normalizer

CLI that normalizes titles/descriptions of full-game videos on the PUL YouTube
channel by matching them to schedule data scraped from the PUL Stats Hub.

- Package: `pul_normalizer/` — run with `python -m pul_normalizer` (dry-run by
  default; `--apply` pushes after confirmation; `--rollback <run-dir>` undoes).
- Single source of team truth: `data/teams_info.json` (names, locations,
  shorts, aliases, hub spellings) via `team_registry.py`.
- Tests: `pytest` (config in `pyproject.toml`). Development is TDD: write the
  failing test first.
- Each run logs to `logs/run_<timestamp>/`; apply runs write `backup.json`
  there before touching YouTube.
- Secrets (`client_secrets.json`, `token.json`) live in the project root,
  gitignored — never commit them. The GitHub repo is public.

## TODO

- [ ] Add a GitHub Actions workflow that runs `pytest` on every push/PR.
- [ ] Add `ruff` (lint) and `mypy` (types) with configs in `pyproject.toml`,
      and wire them into the CI workflow.
- [ ] Replace the synthetic postseason HTML in `tests/test_stats_hub_scraper.py`
      with a real fixture saved from a playoff-season schedule page, to confirm
      the hub's actual markup for Semifinals/Finals sections.
