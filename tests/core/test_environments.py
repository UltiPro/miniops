import json
import os
import subprocess
import sys
from importlib.metadata import distributions
from pathlib import Path

import polars as pl
import pytest

from miniops.core import environments
from miniops.core.entities import Task
from miniops.core.environments import UV_INSTALL, sync_environment
from miniops.core.errors import NotFoundError, ToolError
from miniops.runner.protocol import TrainJob, write_job
from miniops.templates import write_model_files
from miniops.tools import find_tool


def a_model(directory: Path) -> Path:
    directory.mkdir()
    write_model_files(directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)
    return directory


def test_the_environment_is_synced_by_uv_in_the_model_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def run_tool(tool: Path, *arguments: str, env: dict[str, str]) -> None:
        calls.append((tool, arguments, sorted(name for name in env if name.endswith("_ENV"))))
        (Path(arguments[-1]) / ".venv").mkdir()

    monkeypatch.setattr(environments, "find_tool", lambda name: Path(f"/tools/{name}"))
    monkeypatch.setattr(environments, "run_tool", run_tool)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON", "MINIOPS_KEPT_ENV"):
        monkeypatch.setenv(name, "set")
    directory = a_model(tmp_path / "churn")

    sync_environment(directory)

    assert calls == [
        (Path("/tools/uv"), ("sync", "--project", str(directory)), ["MINIOPS_KEPT_ENV"])
    ]


def test_an_environment_that_uv_puts_elsewhere_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(environments, "find_tool", lambda name: Path(f"/tools/{name}"))
    monkeypatch.setattr(environments, "run_tool", lambda tool, *arguments, env: None)

    with pytest.raises(ToolError, match="probably a member of a uv workspace"):
        sync_environment(a_model(tmp_path / "churn"))


def test_without_uv_there_is_no_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(environments, "find_tool", lambda name: None)

    with pytest.raises(ToolError, match=f"uv was not found. Install it: {UV_INSTALL}"):
        sync_environment(a_model(tmp_path / "churn"))


def test_a_model_directory_that_is_missing_or_incomplete_has_no_environment(
    tmp_path: Path,
) -> None:
    with pytest.raises(NotFoundError, match="There is no model directory"):
        sync_environment(tmp_path / "churn")
    with pytest.raises(NotFoundError, match=r"has no pyproject\.toml"):
        sync_environment(tmp_path)


def test_a_new_model_gets_an_environment_that_trains_it(tmp_path: Path) -> None:
    if find_tool("uv") is None or os.environ.get("UV_OFFLINE"):
        pytest.skip("needs uv and the network")
    directory = a_model(tmp_path / "churn")
    # The versions of the tests themselves, so that a new release on PyPI cannot break this.
    pins = sorted(
        {
            f"{found.name}=={found.version}"
            for found in distributions()
            if found.name != "miniops-ml"
        }
    )
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "package = false\n", f"package = false\nconstraint-dependencies = {json.dumps(pins)}\n"
        ),
        encoding="utf-8",
    )

    sync_environment(directory)

    python = (
        directory / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    pl.DataFrame({"age": [21, 35, 47, 52, 23, 61], "churned": [0, 1, 0, 1, 0, 1]}).write_parquet(
        tmp_path / "train.parquet"
    )
    job = TrainJob(
        model="churn",
        entrypoint="model.py:Churn",
        task=Task.BINARY_CLASSIFICATION,
        params={"n_estimators": 5, "random_state": 0},
        data="train.parquet",
        target="churned",
        output="output",
    )
    write_job(job, tmp_path / "job.json")
    finished = subprocess.run(
        [python, "-m", "miniops.runner", str(tmp_path / "job.json")],
        capture_output=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stdout.decode("utf-8", "replace")
    assert (directory / "uv.lock").is_file()
    assert (tmp_path / "output" / "model" / "model.skops").is_file()
