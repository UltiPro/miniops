import platform

import pytest
from typer.testing import CliRunner

from miniops import __version__
from miniops.cli import app

runner = CliRunner()


def test_version_option_prints_short_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"miniops {__version__}"


def test_help_shows_usage() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage" in result.stdout


@pytest.mark.parametrize("command", [["init"], ["config"], ["config", "show"], ["version"]])
def test_every_command_exists_and_has_help(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_an_unknown_command_is_refused() -> None:
    result = runner.invoke(app, ["deploy-to-the-moon", "--help"])

    assert result.exit_code == 2


def test_no_arguments_shows_help() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.output


def test_version_command_reports_python_os_and_architecture() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert platform.python_version() in result.stdout
    assert platform.platform() in result.stdout
    assert platform.machine() in result.stdout
