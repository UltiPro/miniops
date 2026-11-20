import io
import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from miniops.runner.__main__ import main


def run_main(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> int:
    monkeypatch.setattr(sys, "argv", ["runner", *arguments])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert isinstance(exit_info.value.code, int)
    return exit_info.value.code


def test_a_job_that_succeeds_ends_with_0(
    workdir: Path, make_job: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_main(monkeypatch, str(make_job())) == 0
    assert (workdir / "output" / "result.json").is_file()


def test_a_job_that_fails_ends_with_1(
    workdir: Path, make_job: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_main(monkeypatch, str(make_job(target="spend"))) == 1
    assert (workdir / "output" / "result.json").is_file()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ((), "Usage: python -m miniops.runner <job file>"),
        (("first.json", "second.json"), "Usage: python -m miniops.runner <job file>"),
        (("missing.json",), "missing.json"),
    ],
)
def test_a_job_file_that_cannot_be_read_ends_with_1(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    arguments: tuple[str, ...],
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.ERROR, logger="miniops"):
        assert run_main(monkeypatch, *arguments) == 1

    assert message in caplog.text


def test_an_output_that_is_not_a_file_is_used_as_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)

    assert run_main(monkeypatch) == 1
    assert sys.stdout is output


def test_a_job_file_of_another_kind_ends_with_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    job = tmp_path / "job.json"
    job.write_text("{}", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="miniops"):
        assert run_main(monkeypatch, str(job)) == 1

    assert "is not a valid job file" in caplog.text


def test_the_runner_runs_as_a_module_and_logs_in_utf_8_with_warnings(
    workdir: Path, make_job: Callable[..., Path]
) -> None:
    model = (workdir / "model.py").read_text(encoding="utf-8")
    warning = 'warnings.warn("Mało danych 数据")\n        return Pipeline('
    (workdir / "model.py").write_text(
        "import warnings\n" + model.replace("return Pipeline(", warning), encoding="utf-8"
    )

    finished = subprocess.run(
        [sys.executable, "-m", "miniops.runner", str(make_job())], capture_output=True, check=False
    )
    log = finished.stdout.decode("utf-8")

    assert finished.returncode == 0, log + finished.stderr.decode("utf-8", "replace")
    assert "INFO miniops.runner.jobs: Training model.py:Churn" in log
    assert "WARNING py.warnings: " in log
    assert "Mało danych 数据" in log
    assert (workdir / "output" / "model" / "model.skops").is_file()
