import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import polars as pl
import pytest

from miniops.core.entities import Task
from miniops.runner.protocol import TrainJob, write_job
from miniops.templates import write_model_files

DATA = pl.DataFrame(
    {
        "age": [21, 35, 47, 52, 23, 61, 33, 44],
        "visits": [3.0, 1.5, None, 4.0, 2.5, 5.0, 1.0, 3.5],
        "churned": [0, 1, 0, 1, 0, 1, 0, 1],
    }
)


@pytest.fixture(autouse=True)
def separate_runs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The runner changes sys.path, sys.modules and the logging of warnings of its process.
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in ("model", "steps"):
        sys.modules.pop(name, None)
    logging.captureWarnings(False)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    write_model_files(tmp_path, "churn", "sklearn", Task.BINARY_CLASSIFICATION)
    DATA.write_parquet(tmp_path / "train.parquet")
    return tmp_path


@pytest.fixture
def make_job(workdir: Path) -> Callable[..., Path]:
    def make(**changes: object) -> Path:
        fields: dict[str, object] = {
            "model": ".",
            "entrypoint": "model.py:Churn",
            "task": Task.BINARY_CLASSIFICATION,
            "params": {"n_estimators": 5, "random_state": 0},
            "data": "train.parquet",
            "target": "churned",
            "output": "output",
        }
        path = workdir / "job.json"
        write_job(TrainJob.model_validate(fields | changes), path)
        return path

    return make
