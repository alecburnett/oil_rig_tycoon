# Repository Guidelines

## Project Structure & Key Paths
- `rig_tycoon/` core package: `sim.py` orchestrates runs/save/load, `cli.py` is the entrypoint, markets live in `market.py`/`rig_market.py`, contracts in `contracts.py`, models in `models.py`, AI heuristics in `ai.py`.
- `tests/` holds pytest suites (currently `test_save_load.py` for save/load determinism).
- `workings/` contains notebooks for visualization; run against the latest `output/` data.
- `output/` stores timestamped run artifacts (`sim_history_market.csv`, `sim_history_company.csv`).
- `plan/` documents design intent; update when changing bidding/economic logic. `run.sh` wraps the CLI; `requirements.txt` lists deps (Python >=3.11 per `pyproject.toml`).

## Setup, Build & Run
- Create env: `python3 -m venv rig_tycoon_env && source rig_tycoon_env/bin/activate`.
- Install deps: `pip install -r requirements.txt`.
- Run sim: `python3 -m rig_tycoon.cli --months 36 --seed 7` or `./run.sh --months 12 --seed 3`.
- Each run writes under `output/<timestamp>/`; reuse seeds to reproduce cash/market series and notebook visuals.

## Testing Guidelines
- Runner: `python -m pytest -q tests/test_save_load.py`.
- Seed RNGs via `SimConfig` and avoid wall-clock coupling to keep determinism; clean any temp files created by tests.
- Add focused cases around contract generation, market steps, and persistence when extending those modules.

## Coding Style & Naming Conventions
- Python style: 4-space indent, type hints (see `cli.py`, `sim.py`), prefer dataclasses for configs (`SimConfig`).
- Pass around the shared `self.rng` instead of global `random` to keep saves reproducible.
- Naming: snake_case for modules/functions, PascalCase for classes/enums, UPPER_SNAKE for constants.
- When persisting, extend `to_dict`/`from_dict` with version keys and keep backward compatibility for existing saves.
- Formatting is lightweight (no enforced formatter); keep lines readable (~100 chars) and logging minimal but clear.

## Commit & Pull Request Guidelines
- Commits: concise imperative subject (e.g., "Add rig market migration"), scoped changes, include the command/seed used for verification.
- PRs: describe behavior changes and economic impact, list run+test commands, link issues/tasks, attach screenshots/plots for visualization updates, and call out save-format changes explicitly.

## Reproducibility & Data Hygiene
- Control determinism with explicit seeds; document seed changes and expected effects when adjusting AI/markets.
- Keep `output/` artifacts small; avoid committing bulky intermediates. Notebooks should read from latest outputs rather than storing rendered data.
