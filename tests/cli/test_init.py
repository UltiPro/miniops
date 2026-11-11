from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniops.cli import app
from miniops.config.project import find_project
from miniops.core.errors import AlreadyExistsError

runner = CliRunner()


def test_init_creates_a_project_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert repr(tmp_path.name) in result.stdout
    assert find_project(tmp_path).config.project.name == tmp_path.name


def test_init_takes_a_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--name", "retail-models"])

    assert result.exit_code == 0
    assert find_project(tmp_path).config.project.name == "retail-models"


def test_init_twice_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert isinstance(result.exception, AlreadyExistsError)
