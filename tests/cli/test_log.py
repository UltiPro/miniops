import logging
import os
from pathlib import Path

import pytest

from miniops.cli import log
from miniops.cli.log import project_log
from miniops.config.project import init_project

logger = logging.getLogger("miniops.somewhere")


def log_file_of(root: Path) -> Path:
    return root / ".miniops" / "logs" / "miniops.log"


def messages_in(root: Path) -> list[str]:
    lines = log_file_of(root).read_text(encoding="utf-8").splitlines()
    return [line.split("miniops.somewhere: ", 1)[1] for line in lines]


def test_a_command_without_problems_leaves_no_log(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path) as command_log:
        logger.debug("looking for the lock file")
        logger.info("trained churn")

    assert command_log is not None
    assert not command_log.saved
    assert not (tmp_path / ".miniops").exists()


def test_the_first_problem_writes_what_the_command_logged_so_far(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path) as command_log:
        logger.debug("looking for the lock file")
        logger.info("training churn")
        logger.warning("the lock file is older than pyproject.toml")
        assert messages_in(tmp_path) == [
            "looking for the lock file",
            "training churn",
            "the lock file is older than pyproject.toml",
        ]
        logger.info("trained churn")

    assert command_log is not None
    assert command_log.saved
    assert command_log.file == log_file_of(tmp_path)
    assert messages_in(tmp_path)[-1] == "trained churn"


def test_a_line_shows_its_level_and_its_process(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path):
        logger.warning("something is off")

    line = log_file_of(tmp_path).read_text(encoding="utf-8")
    assert f" WARNING [{os.getpid()}] miniops.somewhere: something is off\n" in line


def test_an_error_is_written_with_its_traceback(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path):
        try:
            raise ValueError("not a number")
        except ValueError:
            logger.exception("training failed")

    text = log_file_of(tmp_path).read_text(encoding="utf-8")
    assert "miniops.somewhere: training failed\n" in text
    assert "Traceback (most recent call last)" in text
    assert "ValueError: not a number" in text


def test_every_command_with_a_problem_adds_to_the_same_file(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path):
        logger.error("first")
    with project_log(tmp_path):
        logger.error("second")

    assert messages_in(tmp_path) == ["first", "second"]


def test_the_log_is_found_from_a_directory_inside_the_project(tmp_path: Path) -> None:
    init_project(tmp_path)
    inside = tmp_path / "models" / "churn"
    inside.mkdir(parents=True)

    with project_log(inside):
        logger.error("something broke")

    assert messages_in(tmp_path) == ["something broke"]


def test_outside_a_project_nothing_is_kept(tmp_path: Path) -> None:
    with project_log(tmp_path) as command_log:
        logger.error("nobody keeps this")

    assert command_log is None
    assert list(tmp_path.iterdir()) == []


def test_a_log_that_cannot_be_written_does_not_stop_the_command(tmp_path: Path) -> None:
    init_project(tmp_path)
    (tmp_path / ".miniops").write_text("a file where the directory should be", encoding="utf-8")

    with project_log(tmp_path) as command_log:
        logger.error("something broke")

    assert command_log is not None
    assert not command_log.saved


def test_a_current_directory_that_is_gone_does_not_stop_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def gone() -> Path:
        raise FileNotFoundError("The current directory was removed")

    monkeypatch.setattr(Path, "cwd", staticmethod(gone))

    with project_log() as command_log:
        logger.error("something broke")

    assert command_log is None


def test_a_log_call_that_cannot_be_formatted_does_not_stop_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init_project(tmp_path)
    # pytest listens on the root logger and fails a test on a broken log call.
    monkeypatch.setattr(logging.getLogger("miniops"), "propagate", False)

    with project_log(tmp_path) as command_log:
        logger.warning("%s and %s", "only one")
        assert command_log is not None
        assert not command_log.saved
        logger.warning("a line that works")

    assert "Logging error" in capsys.readouterr().err
    assert messages_in(tmp_path) == ["a line that works"]


def test_text_that_cannot_be_encoded_is_written_with_escapes(tmp_path: Path) -> None:
    init_project(tmp_path)

    with project_log(tmp_path) as command_log:
        logger.error("cannot read %s", "data/\udcff.parquet")

    assert command_log is not None
    assert command_log.saved
    assert messages_in(tmp_path) == ["cannot read data/\\udcff.parquet"]


def test_logging_is_as_before_afterwards(tmp_path: Path) -> None:
    init_project(tmp_path)
    miniops_logger = logging.getLogger("miniops")
    handlers, level = list(miniops_logger.handlers), miniops_logger.level

    with project_log(tmp_path):
        logger.error("something broke")

    assert miniops_logger.handlers == handlers
    assert miniops_logger.level == level


def test_only_the_latest_lines_before_a_problem_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    monkeypatch.setattr(log, "KEPT_RECORDS", 3)

    with project_log(tmp_path):
        for number in range(1, 6):
            logger.info("step %d", number)
        logger.error("step 6 failed")

    assert messages_in(tmp_path) == ["step 4", "step 5", "step 6 failed"]


def test_a_full_log_is_set_aside_when_a_command_has_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    monkeypatch.setattr(log, "MAX_BYTES", 20)
    with project_log(tmp_path):
        logger.error("an old problem, in a line that is longer than the limit")

    with project_log(tmp_path):
        logger.error("a new problem")
        logger.error("and another one in the same command")

    previous = log_file_of(tmp_path).with_name("miniops.log.1")
    assert "an old problem" in previous.read_text(encoding="utf-8")
    assert messages_in(tmp_path) == ["a new problem", "and another one in the same command"]


def test_a_full_log_that_another_process_holds_keeps_growing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    monkeypatch.setattr(log, "MAX_BYTES", 20)
    with project_log(tmp_path):
        logger.error("an old problem, in a line that is longer than the limit")

    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError("The process cannot access the file")

    monkeypatch.setattr(Path, "replace", refuse)
    with project_log(tmp_path):
        logger.error("a new problem")

    assert messages_in(tmp_path) == [
        "an old problem, in a line that is longer than the limit",
        "a new problem",
    ]
