import logging
import platform
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from miniops import __version__
from miniops.core.entities import Column, Signature, Task
from miniops.core.errors import ProtocolError
from miniops.runner.jobs import load_model_class, run
from miniops.runner.protocol import read_result


def test_a_job_trains_the_model_and_leaves_its_files_and_a_result(
    workdir: Path, make_job: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = workdir / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = run(make_job())

    assert result.failure is None
    assert result.signature == Signature(
        inputs=(Column("age", "Int64"), Column("visits", "Float64", nullable=True)),
        outputs=(Column("prediction", "Int64"),),
    )
    assert result.files == ("model.skops",)
    assert result.environment.miniops == __version__
    assert result.environment.python == platform.python_version()
    assert read_result(workdir / "output" / "result.json") == result
    model_class = load_model_class(workdir, "model.py:Churn")
    loaded = model_class.load(
        workdir / "output" / "model", Task.BINARY_CLASSIFICATION, result.untrusted_types
    )
    data = pl.read_parquet(workdir / "train.parquet")
    assert loaded.predict(data).height == data.height


@pytest.mark.parametrize(
    ("changes", "kind", "reported", "message"),
    [
        ({"target": "spend"}, "DataError", True, "The data has no target column 'spend'."),
        (
            {"entrypoint": "model.py:Fraud"},
            "ConfigError",
            True,
            "model.py has no class Fraud, which the entrypoint in model.toml names.",
        ),
        (
            {"entrypoint": "model.py:SklearnModel"},
            "ConfigError",
            True,
            "SklearnModel in model.py does not implement build.",
        ),
        (
            {"entrypoint": "churn.py:Churn"},
            "ConfigError",
            True,
            "churn.py does not exist, but the entrypoint in model.toml names it.",
        ),
        ({"data": "missing.parquet"}, "FileNotFoundError", False, "missing.parquet"),
        ({"params": {"n_estimators": "many"}}, "InvalidParameterError", False, "n_estimators"),
    ],
)
def test_a_failed_training_leaves_a_result_that_says_why(
    workdir: Path,
    make_job: Callable[..., Path],
    changes: dict[str, object],
    kind: str,
    reported: bool,
    message: str,
) -> None:
    result = run(make_job(**changes))

    assert result.failure is not None
    assert (result.failure.type, result.failure.reported) == (kind, reported)
    assert message in result.failure.message
    assert result.signature is None
    assert read_result(workdir / "output" / "result.json") == result


def test_a_class_that_is_not_a_model_is_refused(
    workdir: Path, make_job: Callable[..., Path]
) -> None:
    (workdir / "model.py").write_text("class Churn:\n    pass\n", encoding="utf-8")

    result = run(make_job())

    assert result.failure is not None
    assert result.failure.message == (
        "Churn in model.py is not a model class: it has to subclass the base class of a flavor, "
        "like SklearnModel."
    )


def test_a_model_file_missing_from_its_directory_is_not_looked_for_elsewhere(
    workdir: Path, make_job: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = workdir / "elsewhere"
    elsewhere.mkdir()
    (workdir / "model.py").replace(elsewhere / "model.py")
    monkeypatch.chdir(elsewhere)
    monkeypatch.syspath_prepend(str(elsewhere))

    result = run(make_job())

    assert result.failure is not None
    assert result.failure.type == "ConfigError"
    assert "does not exist" in result.failure.message


@pytest.mark.parametrize("file_name", ["json.py", "polars.py"])
def test_a_model_file_named_like_a_module_in_use_is_refused(
    workdir: Path, make_job: Callable[..., Path], file_name: str
) -> None:
    (workdir / "model.py").replace(workdir / file_name)

    result = run(make_job(entrypoint=f"{file_name}:Churn"))

    assert result.failure is not None
    assert result.failure.message == (
        f"{file_name} has the name of a Python module that is in use. Rename the file and the "
        "entrypoint in model.toml."
    )


def test_model_code_that_exits_has_failed(workdir: Path, make_job: Callable[..., Path]) -> None:
    model = (workdir / "model.py").read_text(encoding="utf-8")
    (workdir / "model.py").write_text(
        "import sys\n" + model.replace("return Pipeline(", "sys.exit(3)\n        return Pipeline("),
        encoding="utf-8",
    )

    result = run(make_job())

    assert result.failure is not None
    assert (result.failure.type, result.failure.message) == (
        "SystemExit",
        "The model code called sys.exit(3).",
    )


def test_the_traceback_of_a_failure_goes_to_the_log(
    make_job: Callable[..., Path], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="miniops"):
        run(make_job(target="spend"))

    [failure] = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert failure.getMessage() == "The training failed"
    assert failure.exc_info is not None


def test_the_model_can_import_its_own_modules(workdir: Path, make_job: Callable[..., Path]) -> None:
    (workdir / "steps.py").write_text("ESTIMATORS = 3\n", encoding="utf-8")
    model = (workdir / "model.py").read_text(encoding="utf-8")
    (workdir / "model.py").write_text(
        "from steps import ESTIMATORS\n"
        + model.replace("(**params)", "(n_estimators=ESTIMATORS, random_state=0)"),
        encoding="utf-8",
    )

    assert run(make_job(params={})).failure is None


def test_the_output_of_an_earlier_job_is_left_alone(
    workdir: Path, make_job: Callable[..., Path]
) -> None:
    job = make_job()
    run(job)
    files = {path: path.read_bytes() for path in (workdir / "output").rglob("*") if path.is_file()}

    with pytest.raises(FileExistsError):
        run(job)

    assert {path: path.read_bytes() for path in files} == files


def test_a_job_file_that_cannot_be_read_leaves_no_result(workdir: Path) -> None:
    job = workdir / "job.json"
    job.write_text("{}", encoding="utf-8")

    with pytest.raises(ProtocolError, match="is not a valid job file"):
        run(job)

    assert not (workdir / "output").exists()
