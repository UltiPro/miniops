import runpy
import sys
from pathlib import Path

import pytest

from miniops import __version__
from miniops.cli import main


def test_module_entry_point_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["miniops", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("miniops", run_name="__main__")

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"miniops {__version__}"


def test_an_error_that_miniops_reports_ends_with_a_message_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["miniops", "config", "show"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: No miniOPs project")
    assert "Traceback" not in captured.err
    assert captured.out == ""
