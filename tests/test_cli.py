from pathlib import Path

import pytest
from typer.testing import CliRunner

from sprig import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def stub_external_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid hitting git or make during smoke tests."""
    monkeypatch.setattr(cli, "git_pull", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "ensure_git_clean", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "run_make_setup", lambda *args, **kwargs: None)


@pytest.fixture()
def repo(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root: Path = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)
    return root


def test_new_scaffolds_workspace(runner: CliRunner, repo) -> None:
    result = runner.invoke(cli.app, ["new", "demo"])

    assert result.exit_code == 0
    workspace = repo / ".workspaces" / "demo"
    assert workspace.is_dir()
    assert (workspace / "config.yaml").exists()
    assert (workspace / "README.md").exists()
    assert ".workspaces/" in (repo / ".gitignore").read_text()


def test_init_alias_defaults_to_repo_name(runner: CliRunner, repo) -> None:
    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    workspace = repo / ".workspaces" / repo.name
    assert workspace.is_dir()
