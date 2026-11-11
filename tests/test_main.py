import runpy
import sys

import pytest

from miniops import __version__


def test_module_entry_point_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["miniops", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("miniops", run_name="__main__")

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"miniops {__version__}"
