import runpy
import sys
from pathlib import Path

import pytest

from miniops import __version__
from miniops.cli import config, main
from miniops.config.project import init_project


def run(monkeypatch: pytest.MonkeyPatch, directory: Path, *arguments: str) -> int:
    monkeypatch.chdir(directory)
    monkeypatch.setattr(sys, "argv", ["miniops", *arguments])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert isinstance(exit_info.value.code, int)
    return exit_info.value.code


def log_of(project: Path) -> str:
    return (project / ".miniops" / "logs" / "miniops.log").read_text(encoding="utf-8")


def boom(start: Path) -> None:
    raise RuntimeError("boom")


def test_module_entry_point_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["miniops", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("miniops", run_name="__main__")

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"miniops {__version__}"


def test_a_command_that_needs_no_directory_works_when_the_current_one_is_gone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gone() -> Path:
        raise FileNotFoundError("The current directory was removed")

    monkeypatch.setattr(Path, "cwd", staticmethod(gone))
    monkeypatch.setattr(sys, "argv", ["miniops", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"miniops {__version__}"


def test_a_command_that_succeeds_leaves_no_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)

    assert run(monkeypatch, tmp_path, "config", "show") == 0

    assert not (tmp_path / ".miniops").exists()


def test_an_error_that_miniops_reports_ends_with_a_message_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, tmp_path, "config", "show") == 1

    captured = capsys.readouterr()
    assert captured.err.startswith("Error: No miniOPs project")
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_the_traceback_of_a_reported_error_is_in_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)

    assert run(monkeypatch, tmp_path, "init") == 1

    assert capsys.readouterr().err.startswith("Error: There is already a miniOPs project")
    log = log_of(tmp_path)
    assert f"miniops.cli: miniops {__version__}: init\n" in log
    assert " ERROR " in log
    assert "Command failed: There is already a miniOPs project" in log
    assert "Traceback (most recent call last)" in log
    assert "AlreadyExistsError" in log


def test_an_unexpected_error_shows_where_the_details_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)
    monkeypatch.setattr(config, "find_project", boom)

    assert run(monkeypatch, tmp_path, "config", "show") == 1

    log_file = tmp_path / ".miniops" / "logs" / "miniops.log"
    assert capsys.readouterr().err.splitlines() == [
        "Error: miniOPs hit an unexpected error (RuntimeError: boom). This is a bug.",
        f"Details: {log_file}",
    ]
    log = log_of(tmp_path)
    assert f"miniops.cli: miniops {__version__}: config show\n" in log
    assert " CRITICAL " in log
    assert "Traceback (most recent call last)" in log
    assert "RuntimeError: boom" in log


def test_an_unexpected_error_is_not_hidden_when_the_log_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    (tmp_path / ".miniops").write_text("a file where the directory should be", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["miniops", "config", "show"])
    monkeypatch.setattr(config, "find_project", boom)

    with pytest.raises(RuntimeError, match="boom"):
        main()


def test_an_unexpected_error_outside_a_project_is_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["miniops", "config", "show"])
    monkeypatch.setattr(config, "find_project", boom)

    with pytest.raises(RuntimeError, match="boom"):
        main()
