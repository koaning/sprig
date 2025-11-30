from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

import typer

from . import __version__

app = typer.Typer(help="Manage agent workspaces inside a git repo.", invoke_without_command=False)
branch_app = typer.Typer(help="Commands meant to run from inside a workspace.")
app.add_typer(branch_app, name="branch")

WORKSPACES_DIR = ".workspaces"
DEFAULT_BRANCH = "main"
BRANCH_ENV = "AGENT_WS_BRANCH"
SKIP_SETUP_ENV = "AGENT_WS_SKIP_SETUP"


class SprigError(Exception):
    """Raised for expected, user-facing errors."""


def echo(message: str, quiet: bool = False) -> None:
    if not quiet:
        typer.echo(message)


def truthy(value: Optional[str]) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def find_repo_root(start: Path) -> Optional[Path]:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def detect_workspace(cwd: Path, root: Path) -> Optional[str]:
    try:
        relative = cwd.resolve().relative_to(root.resolve())
    except ValueError:
        return None

    parts = relative.parts
    if len(parts) >= 2 and parts[0] == WORKSPACES_DIR:
        return parts[1]
    return None


def ensure_root_command(cwd: Path) -> Path:
    root = find_repo_root(cwd)
    if root is None:
        raise SprigError("sprig must run inside a git repository.")

    if detect_workspace(cwd, root):
        raise SprigError("Run this command from the repo root, not inside a workspace.")

    if cwd.resolve() != root.resolve():
        raise SprigError(f"Run this command from the repo root: {root}")

    return root


def ensure_workspace_command(cwd: Path) -> tuple[Path, str]:
    root = find_repo_root(cwd)
    if root is None:
        raise SprigError("sprig must run inside a git repository.")

    workspace = detect_workspace(cwd, root)
    if not workspace:
        raise SprigError("This command is only available inside a workspace under .workspaces/.")

    return root, workspace


def run_command(args: Iterable[str], cwd: Path, quiet: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            list(args),
            cwd=cwd,
            check=True,
            text=True,
            stdout=None if not quiet else subprocess.PIPE,
            stderr=None if not quiet else subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SprigError(f"Command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SprigError(f"Command failed ({' '.join(args)}): {exc}") from exc


def ensure_git_clean(root: Path, force: bool) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout.strip() and not force:
        raise SprigError("Working tree is dirty. Commit, stash, or re-run with --force.")


def git_pull(root: Path, branch: str, quiet: bool) -> None:
    echo(f"Pulling from origin/{branch}...", quiet)
    run_command(["git", "pull", "origin", branch], cwd=root, quiet=quiet)


def ensure_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    entry = f"{WORKSPACES_DIR}/"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in {line.strip() for line in content.splitlines()}:
            return
        gitignore.write_text(content + ("\n" if not content.endswith("\n") else "") + entry + "\n")
    else:
        gitignore.write_text(f"{entry}\n")


def scaffold_config(workspace_dir: Path) -> None:
    config = workspace_dir / "config.yaml"
    if config.exists():
        return

    config.write_text(
        "\n".join(
            [
                "# sprig workspace config",
                "agent: \"\"",
                "notes: \"\"",
                "paths: []",
                "env_file: \"\"",
                "",
            ]
        )
    )

    readme = workspace_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    f"# Workspace `{workspace_dir.name}`",
                    "",
                    "This directory is meant for agent-driven changes. Keep human notes in `config.yaml`.",
                    "",
                ]
            )
        )


def run_make_setup(root: Path, quiet: bool) -> None:
    makefile = root / "Makefile"
    if not makefile.exists():
        echo("Skipping `make setup` (no Makefile found).", quiet)
        return

    echo("Running `make setup`...", quiet)
    try:
        run_command(["make", "setup"], cwd=root, quiet=quiet)
    except SprigError as exc:
        raise SprigError(f"`make setup` failed: {exc}") from exc


@app.command()
def version() -> None:
    """Show the sprig version."""
    typer.echo(__version__)


@app.command()
def new(
    name: Optional[str] = typer.Argument(None, help="Workspace name (defaults to repo name)."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch to pull before creating."),
    no_setup: bool = typer.Option(False, "--no-setup", help="Skip `make setup`."),
    force: bool = typer.Option(False, "--force", help="Proceed even if the working tree is dirty or workspace exists."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce output."),
) -> None:
    """Create a new workspace from the repo root."""
    _create_workspace(name, branch, no_setup, force, quiet)


@app.command()
def init(
    name: Optional[str] = typer.Argument(None, help="Workspace name (defaults to repo name)."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch to pull before creating."),
    no_setup: bool = typer.Option(False, "--no-setup", help="Skip `make setup`."),
    force: bool = typer.Option(False, "--force", help="Proceed even if the working tree is dirty or workspace exists."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce output."),
) -> None:
    """Alias for `sprig new`."""
    _create_workspace(name, branch, no_setup, force, quiet)


def _create_workspace(
    name: Optional[str],
    branch: Optional[str],
    no_setup: bool,
    force: bool,
    quiet: bool,
) -> None:
    cwd = Path.cwd()
    root = ensure_root_command(cwd)

    target_branch = branch or os.environ.get(BRANCH_ENV) or DEFAULT_BRANCH
    skip_setup = no_setup or truthy(os.environ.get(SKIP_SETUP_ENV))
    workspace_name = name or root.name
    workspace_dir = root / WORKSPACES_DIR / workspace_name

    git_pull(root, target_branch, quiet)
    ensure_git_clean(root, force)

    if workspace_dir.exists():
        if not force:
            raise SprigError(f"Workspace {workspace_name} already exists. Use --force to overwrite.")
        shutil.rmtree(workspace_dir)

    workspace_dir.mkdir(parents=True, exist_ok=True)
    scaffold_config(workspace_dir)
    ensure_gitignore(root)

    if not skip_setup:
        run_make_setup(root, quiet)
    else:
        echo("Skipping `make setup` (flag or env set).", quiet)

    echo(f"Workspace ready at {workspace_dir.relative_to(root)}", quiet)
    echo(f"Next: cd {workspace_dir.relative_to(root)}", quiet)


@app.command()
def list() -> None:
    """List available workspaces (repo root only)."""
    cwd = Path.cwd()
    root = ensure_root_command(cwd)
    workspaces_root = root / WORKSPACES_DIR
    if not workspaces_root.exists():
        typer.echo("No workspaces yet.")
        return

    names = sorted(p.name for p in workspaces_root.iterdir() if p.is_dir())
    if not names:
        typer.echo("No workspaces yet.")
        return

    for name in names:
        typer.echo(name)


@app.command()
def clean(
    name: str = typer.Argument(..., help="Workspace name to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove a workspace (repo root only)."""
    cwd = Path.cwd()
    root = ensure_root_command(cwd)
    workspace_dir = root / WORKSPACES_DIR / name

    if not workspace_dir.exists():
        raise SprigError(f"Workspace {name} does not exist at {workspace_dir}.")

    if not yes:
        if not typer.confirm(f"Remove workspace {workspace_dir}?"):
            raise typer.Exit(code=0)

    shutil.rmtree(workspace_dir)
    typer.echo(f"Removed {workspace_dir.relative_to(root)}")


@branch_app.command("status")
def branch_status() -> None:
    """Show status when inside a workspace."""
    cwd = Path.cwd()
    root, workspace = ensure_workspace_command(cwd)

    branch_name = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    ).stdout.strip()

    typer.echo(f"Repo root: {root}")
    typer.echo(f"Workspace: {workspace}")
    typer.echo(f"Git branch: {branch_name or 'unknown'}")

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    ).stdout.strip()

    typer.echo("Git status:")
    typer.echo(status or "  clean")


@branch_app.command("clean")
def branch_clean() -> None:
    """Inform how to clean from within a workspace."""
    cwd = Path.cwd()
    root, workspace = ensure_workspace_command(cwd)
    typer.echo(f"You are inside .workspaces/{workspace}.")
    typer.echo(f"Run `cd {root}` then `sprig clean {workspace}` to remove this workspace.")


def main() -> None:
    try:
        app()
    except SprigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    main()
