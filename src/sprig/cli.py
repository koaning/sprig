from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

import typer

from . import __version__

app = typer.Typer(
    help="Manage agent workspaces inside a git repo.",
    invoke_without_command=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
branch_app = typer.Typer(
    help="Commands meant to run from inside a workspace.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(branch_app, name="branch")

WORKSPACES_DIR = ".workspaces"
DEFAULT_BRANCH = "main"
BRANCH_ENV = "AGENT_WS_BRANCH"
SKIP_SETUP_ENV = "AGENT_WS_SKIP_SETUP"
SKIP_GIT_ENV = "AGENT_WS_SKIP_GIT"
DEFAULT_WORKSPACE_BRANCH_PREFIX = "workspace/"


class SprigError(Exception):
    """Raised for expected, user-facing errors."""


def echo(message: str, quiet: bool = False) -> None:
    if not quiet:
        typer.echo(message)


def handle_cli_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SprigError as exc:
            echo(f"Error: {exc}")
            raise typer.Exit(code=1) from None

    return wrapper


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
        cmd = [*args]
        return subprocess.run(
            cmd,
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


def git_fetch(root: Path, branch: str, quiet: bool) -> None:
    echo(f"Fetching origin/{branch}...", quiet)
    try:
        run_command(["git", "fetch", "origin", branch], cwd=root, quiet=quiet)
    except SprigError as exc:
        raise SprigError(
            f"Git pull failed for origin/{branch}. If you're offline or in CI, set {SKIP_GIT_ENV}=1."
        ) from exc


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
@handle_cli_errors
def new(
    name: str = typer.Argument(..., help="Workspace name."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch to pull before creating."),
    workspace_branch: Optional[str] = typer.Option(
        None, "--workspace-branch", "-w", help="Branch name for the new workspace (defaults to workspace/<name>)."
    ),
    no_setup: bool = typer.Option(False, "--no-setup", help="Skip `make setup`."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing workspace if present."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce output."),
) -> None:
    """Create a new workspace from the repo root."""
    _create_workspace(name, branch, workspace_branch, no_setup, force, quiet)


@app.command()
@handle_cli_errors
def init(
    quiet: bool = typer.Option(False, "--quiet", help="Reduce output."),
) -> None:
    """Prepare repo for sprig by ensuring .workspaces is ignored."""
    cwd = Path.cwd()
    root = ensure_root_command(cwd)
    ensure_gitignore(root)
    echo(f"Ensured {WORKSPACES_DIR}/ is in .gitignore.", quiet)


def _create_workspace(
    name: str,
    branch: Optional[str],
    workspace_branch: Optional[str],
    no_setup: bool,
    force: bool,
    quiet: bool,
) -> None:
    cwd = Path.cwd()
    root = ensure_root_command(cwd)

    target_branch = branch or os.environ.get(BRANCH_ENV) or DEFAULT_BRANCH
    skip_setup = no_setup or truthy(os.environ.get(SKIP_SETUP_ENV))
    skip_git = truthy(os.environ.get(SKIP_GIT_ENV))
    workspace_dir = root / WORKSPACES_DIR / name
    branch_name = workspace_branch or f"{DEFAULT_WORKSPACE_BRANCH_PREFIX}{name}"

    if skip_git:
        echo("Skipping git pull/clean (testing or override).", quiet)
        prepare_directory_only(workspace_dir, force)
    else:
        git_fetch(root, target_branch, quiet)
        create_git_worktree(root, workspace_dir, branch_name, target_branch, force, quiet)
    scaffold_config(workspace_dir)
    ensure_gitignore(root)

    if not skip_setup:
        run_make_setup(root, quiet)
    else:
        echo("Skipping `make setup` (flag or env set).", quiet)

    echo(f"Workspace ready at {workspace_dir.relative_to(root)}", quiet)
    echo(f"Next: cd {workspace_dir.relative_to(root)}", quiet)


@app.command()
@handle_cli_errors
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
@handle_cli_errors
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
@handle_cli_errors
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
@handle_cli_errors
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
        echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    main()
def prepare_directory_only(workspace_dir: Path, force: bool) -> None:
    if workspace_dir.exists():
        if not force:
            raise SprigError(f"Workspace {workspace_dir.name} already exists. Use --force to overwrite.")
        shutil.rmtree(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)


def branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0


def create_git_worktree(
    root: Path,
    workspace_dir: Path,
    workspace_branch: str,
    base_branch: str,
    force: bool,
    quiet: bool,
) -> None:
    base_ref = f"origin/{base_branch}"

    if workspace_dir.exists():
        if not force:
            raise SprigError(f"Workspace {workspace_dir.name} already exists. Use --force to overwrite.")
        run_command(["git", "worktree", "remove", "--force", str(workspace_dir)], cwd=root, quiet=quiet)
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

    if branch_exists(root, workspace_branch):
        if not force:
            raise SprigError(f"Branch {workspace_branch} already exists. Use --force to overwrite.")
        run_command(["git", "branch", "-D", workspace_branch], cwd=root, quiet=quiet)

    echo(f"Creating worktree at {workspace_dir} on {workspace_branch} from {base_ref}...", quiet)
    run_command(["git", "worktree", "add", "-B", workspace_branch, str(workspace_dir), base_ref], cwd=root, quiet=quiet)
