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

- `sprig new [name]` (or `sprig init [name]`): run from the repo root. Pulls `origin/<branch>`, checks cleanliness, scaffolds `.workspaces/<name>` (defaults to repo name), updates `.gitignore`, and runs `make setup` unless skipped.
- `sprig list`: run from the repo root to list workspaces.
- `sprig clean <name>`: run from the repo root to remove a workspace (prompted unless `--yes`).
- `sprig branch status`: run from inside a workspace to see repo + git status.
- `sprig branch clean`: run from inside a workspace to get a safe removal hint.

## Flags and env

- `--branch/-b` or `AGENT_WS_BRANCH` to choose pull target (default `main`).
- `--no-setup` or `AGENT_WS_SKIP_SETUP=1` to skip `make setup`.
- `--force` to ignore dirty tree and overwrite an existing workspace.
- `--quiet` to reduce output from `sprig new`.
