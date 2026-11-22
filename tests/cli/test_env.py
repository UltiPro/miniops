from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniops.cli import app, env
from miniops.config.project import init_project
from miniops.core.errors import ConfigError, NotFoundError

runner = CliRunner()


def test_env_sync_syncs_the_environment_of_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(env, "sync_environment", synced.append)
    init_project(tmp_path)
    inside = tmp_path / "notebooks"
    inside.mkdir()
    monkeypatch.chdir(inside)

    result = runner.invoke(app, ["env", "sync", "churn"])

    assert result.exit_code == 0
    assert synced == [tmp_path / "models" / "churn"]


def test_env_sync_needs_a_model_directory_with_pyproject_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["env", "sync", "churn"])

    assert result.exit_code == 1
    assert isinstance(result.exception, NotFoundError)


def test_env_sync_needs_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["env", "sync", "churn"])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)


@pytest.mark.parametrize("name", ["Churn", "../churn", "nul"])
def test_env_sync_refuses_a_name_that_is_not_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["env", "sync", name]).exit_code == 2
