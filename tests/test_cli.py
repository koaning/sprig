from pathlib import Path

import pytest
from typer.testing import CliRunner

from sprig import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def repo(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root: Path = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)
    return root


@pytest.fixture(autouse=True)
def skip_external_invocations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid git/make side effects while keeping test config explicit."""
    monkeypatch.setenv(cli.SKIP_GIT_ENV, "1")
    monkeypatch.setenv(cli.SKIP_SETUP_ENV, "1")


def test_new_scaffolds_workspace(runner: CliRunner, repo) -> None:
    result = runner.invoke(cli.app, ["new", "demo"])

    assert result.exit_code == 0
    workspace = repo / ".workspaces" / "demo"
    assert workspace.is_dir()
    assert (workspace / "config.yaml").exists()
    assert (workspace / "README.md").exists()
    assert ".workspaces/" in (repo / ".gitignore").read_text()


def test_init_checks_gitignore(runner: CliRunner, repo) -> None:
    gitignore = repo / ".gitignore"
    gitignore.write_text("")  # start empty

    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert ".workspaces/" in gitignore.read_text()


def test_new_requires_name(runner: CliRunner, repo) -> None:
    result = runner.invoke(cli.app, ["new"])

    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_run_command_not_broken_by_list_shadow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = {}

    def fake_run(cmd, cwd, check, text, stdout, stderr):
        calls["cmd"] = cmd

        class Result:
            pass

        return Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "list", lambda *args, **kwargs: (_ for _ in ()).throw(TypeError("shadowed")))

    cli.run_command(("echo", "hi"), cwd=tmp_path, quiet=True)

    assert calls["cmd"] == ["echo", "hi"]


def test_git_pull_failure_is_user_friendly(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, repo: Path) -> None:
    monkeypatch.setenv(cli.SKIP_GIT_ENV, "")  # allow git path
    monkeypatch.setenv(cli.SKIP_SETUP_ENV, "1")  # still skip make
    monkeypatch.setattr(cli, "run_command", lambda *args, **kwargs: (_ for _ in ()).throw(cli.SprigError("boom")))
    messages = []

    def capture_echo(message, *args, **kwargs):
        messages.append(str(message))

    monkeypatch.setattr(cli, "echo", capture_echo)
    monkeypatch.setattr(cli.typer, "echo", capture_echo)

    result = runner.invoke(cli.app, ["new", "demo"])

    assert result.exit_code != 0
    assert any("Git pull failed" in msg for msg in messages)
    assert all("Traceback" not in msg for msg in messages)


def test_new_allows_dirty_tree(runner: CliRunner, repo: Path) -> None:
    dirty_file = repo / "untracked.txt"
    dirty_file.write_text("dirty")

    result = runner.invoke(cli.app, ["new", "demo"])

    assert result.exit_code == 0
