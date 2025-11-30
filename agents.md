# Agents Guide

- Install or run via `uv` (preferred): `uv tool install .` or `uv run sprig --help`.
- From the repo root, make a workspace with `sprig new <name>` (alias: `sprig init <name>`); it pulls `origin/<branch>` (default `main`), checks cleanliness, and scaffolds `.workspaces/<name>`.
- Work inside `.workspaces/<name>`; keep notes in `config.yaml` or its README.
- List and remove workspaces from the repo root: `sprig list` and `sprig clean <name>`.
- From inside a workspace, check status with `sprig branch status`; to remove, go to repo root and run `sprig clean`.
- Tests: prefer pytest fixtures to manage temp dirs/cleanup instead of inline monkeypatching.
