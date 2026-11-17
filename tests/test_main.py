import os
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


def denied(start: Path) -> None:
    raise PermissionError(13, "Permission denied", "miniops.toml")


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


def test_a_reported_error_leaves_the_command_and_the_message_in_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)

    assert run(monkeypatch, tmp_path, "init") == 1

    [error] = capsys.readouterr().err.splitlines()
    assert error.startswith("Error: There is already a miniOPs project")
    command, failure = log_of(tmp_path).splitlines()
    assert command.endswith(f" INFO [{os.getpid()}] miniops.cli: miniops {__version__}: init")
    assert " ERROR " in failure
    assert failure.endswith(f"miniops.cli: Command failed: {error.removeprefix('Error: ')}")


def test_a_problem_of_the_system_shows_its_message_and_where_the_details_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)
    monkeypatch.setattr(config, "find_project", denied)

    assert run(monkeypatch, tmp_path, "config", "show") == 1

    log_file = tmp_path / ".miniops" / "logs" / "miniops.log"
    assert capsys.readouterr().err.splitlines() == [
        "Error: Permission denied: miniops.toml",
        f"Details: {log_file}",
    ]
    log = log_of(tmp_path)
    assert "Command failed: Permission denied: miniops.toml\n" in log
    assert "Traceback (most recent call last)" in log


def test_a_problem_of_the_system_outside_a_project_shows_only_its_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(config, "find_project", denied)

    assert run(monkeypatch, tmp_path, "config", "show") == 1

    assert capsys.readouterr().err.splitlines() == ["Error: Permission denied: miniops.toml"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        (
            PermissionError(13, "Permission denied", r"C:\project\miniops.toml"),
            r"Permission denied: C:\project\miniops.toml",
        ),
        (
            OSError(18, "Invalid cross-device link", "model.part", None, "model.skops"),
            "Invalid cross-device link: model.part -> model.skops",
        ),
        (OSError(28, "No space left on device"), "No space left on device"),
        (OSError("Cannot use the store: disk I/O error"), "Cannot use the store: disk I/O error"),
    ],
)
def test_a_problem_of_the_system_names_its_files_as_they_are(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    problem: OSError,
    message: str,
) -> None:
    def fail(start: Path) -> None:
        raise problem

    monkeypatch.setattr(config, "find_project", fail)

    assert run(monkeypatch, tmp_path, "config", "show") == 1

    assert capsys.readouterr().err.splitlines() == [f"Error: {message}"]


def test_a_removed_current_directory_is_named_in_the_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def gone() -> Path:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(Path, "cwd", staticmethod(gone))
    monkeypatch.setattr(sys, "argv", ["miniops", "config", "show"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert capsys.readouterr().err.splitlines() == [
        "Error: The current directory does not exist any more."
    ]


def test_a_file_in_the_way_of_a_new_model_is_not_called_a_bug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)
    (tmp_path / "models").write_text("not a directory", encoding="utf-8")

    arguments = ["new", "churn", "--flavor", "sklearn", "--task", "regression"]
    assert run(monkeypatch, tmp_path, *arguments) == 1

    error, details = capsys.readouterr().err.splitlines()
    assert error.startswith("Error: ")
    assert error.endswith(f": {tmp_path / 'models'}")
    assert "bug" not in error
    assert details == f"Details: {tmp_path / '.miniops' / 'logs' / 'miniops.log'}"


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
