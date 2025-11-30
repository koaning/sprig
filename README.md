# sprig

CLI for creating agent-friendly workspaces inside a git repo.

## Installation

This is a standard `pyproject.toml` project. With `uv`:

```bash
uv tool install .
```

Or run ad-hoc:

```bash
uv run sprig --help
```

## Commands

- `sprig init`: run from the repo root. Ensures `.workspaces/` is listed in `.gitignore` for safe workspace usage.
- `sprig new <name>`: run from the repo root. Fetches `origin/<branch>`, creates a git worktree on branch `workspace/<name>` (configurable via `-w`), scaffolds `.workspaces/<name>`, updates `.gitignore`, and runs `make setup` unless skipped.
- `sprig list`: run from the repo root to list workspaces.
- `sprig clean <name>`: run from the repo root to remove a workspace (prompted unless `--yes`).
- `sprig branch status`: run from inside a workspace to see repo + git status.
- `sprig branch clean`: run from inside a workspace to get a safe removal hint.

## Flags and env

- `--branch/-b` or `AGENT_WS_BRANCH` to choose pull target (default `main`).
- `--no-setup` or `AGENT_WS_SKIP_SETUP=1` to skip `make setup`.
- `AGENT_WS_SKIP_GIT=1` to skip git pull/clean (useful in CI/tests only).
- `--force` to ignore dirty tree and overwrite an existing workspace.
- `--quiet` to reduce output from `sprig new`.
