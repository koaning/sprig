# Agents Guide

- Install or run via `uv` (preferred): `uv tool install .` or `uv run sprig --help`.
- Initialize the repo with `sprig init` to ensure `.workspaces/` is in `.gitignore`.
- From the repo root, make a workspace with `sprig new <name>`; it fetches `origin/<branch>` (default `main`) and creates a git worktree under `.workspaces/<name>` on branch `workspace/<name>` by default.
- Work inside `.workspaces/<name>`; keep notes in `config.yaml` or its README.
- List and remove workspaces from the repo root: `sprig list` and `sprig clean <name>`.
- From inside a workspace, check status with `sprig branch status`; to remove, go to repo root and run `sprig clean`.
- Tests: prefer pytest fixtures to manage temp dirs/cleanup instead of inline monkeypatching; use `AGENT_WS_SKIP_GIT=1` (and `AGENT_WS_SKIP_SETUP=1`) to avoid external git/make calls in tests.
