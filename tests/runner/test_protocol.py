import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from miniops import __version__
from miniops.core.entities import Column, Signature, Task
from miniops.core.errors import ProtocolError
from miniops.runner.protocol import (
    Environment,
    Failure,
    Result,
    TrainJob,
    read_job,
    read_result,
    write_job,
    write_result,
)

JOB = TrainJob(
    model="model",
    entrypoint="model.py:Churn",
    task=Task.REGRESSION,
    params={"n_estimators": 300, "max_depth": None, "features": ["age"]},
    data="data/train.parquet",
    target="revenue",
    output="output",
)
ENVIRONMENT = Environment(miniops="0.1.0", python="3.12.16", platform="Linux", machine="x86_64")


def test_a_job_reads_back_as_it_was_written(tmp_path: Path) -> None:
    path = tmp_path / "job.json"

    write_job(JOB, path)

    assert read_job(path) == JOB
    assert json.loads(path.read_text(encoding="utf-8"))["protocol"] == 1


def test_infinity_and_nan_in_params_survive(tmp_path: Path) -> None:
    path = tmp_path / "job.json"

    write_job(JOB.model_copy(update={"params": {"C": math.inf, "tol": math.nan}}), path)

    params = read_job(path).params
    assert params["C"] == math.inf
    assert isinstance(params["tol"], float)
    assert math.isnan(params["tol"])


def test_a_path_with_a_backslash_is_refused() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        TrainJob.model_validate(JOB.model_dump() | {"data": "data\\train.parquet"})


@pytest.mark.parametrize(
    "result",
    [
        Result(
            environment=ENVIRONMENT,
            signature=Signature(
                inputs=(Column("age", "Int64", nullable=True),),
                outputs=(Column("prediction", "Float64"),),
            ),
            files=("model.skops",),
            untrusted_types=("sklearn.tree._tree.Tree",),
        ),
        Result(
            environment=ENVIRONMENT,
            failure=Failure(type="DataError", message="The data has no rows.", reported=True),
        ),
    ],
)
def test_a_result_reads_back_as_it_was_written(tmp_path: Path, result: Result) -> None:
    path = tmp_path / "result.json"

    write_result(result, path)

    assert read_result(path) == result
    assert list(tmp_path.iterdir()) == [path]


def test_a_file_of_a_newer_protocol_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"protocol": 2, "anything": "new"}), encoding="utf-8")

    with pytest.raises(
        ProtocolError,
        match=f"uses protocol 2, but miniOPs {__version__} reads up to protocol 1",
    ):
        read_result(path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not json", "is not a job file of miniOPs"),
        ('{"protocol": 1}'.encode("utf-16"), "is not a job file of miniOPs"),
        (b'{"protocol": 1, "kind": "evaluate"}', "is not a valid job file"),
        (b'["a list"]', "is not a valid job file"),
    ],
)
def test_a_file_that_is_not_a_job_is_refused(tmp_path: Path, content: bytes, message: str) -> None:
    path = tmp_path / "job.json"
    path.write_bytes(content)

    with pytest.raises(ProtocolError, match=message):
        read_job(path)
