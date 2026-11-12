from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniops.cli import app
from miniops.config.project import init_project
from miniops.core.errors import ConfigError

runner = CliRunner()


def test_config_show_prints_the_project_from_anywhere_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path, "retail-models")
    inside = tmp_path / "models"
    inside.mkdir()
    monkeypatch.chdir(inside)

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        f"Project root    {tmp_path}",
        "Name            retail-models",
        "Default target  local",
    ]


def test_config_show_needs_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
