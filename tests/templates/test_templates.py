import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from miniops import __version__, templates
from miniops.config.model import Flavor, load_model_config
from miniops.core.entities import Task
from miniops.core.errors import NotFoundError
from miniops.flavors.sklearn import SklearnModel
from miniops.templates import write_model_files

DATA = pl.DataFrame({"age": [21, 35, 47, 52, 23, 61], "target": [0, 1, 1, 0, 1, 0]})


def model_class(directory: Path) -> type[SklearnModel]:
    file_name, class_name = load_model_config(directory).model.entrypoint.split(":")
    namespace: dict[str, Any] = {}
    exec(compile((directory / file_name).read_text(encoding="utf-8"), file_name, "exec"), namespace)
    found = namespace[class_name]
    assert isinstance(found, type)
    assert issubclass(found, SklearnModel)
    return found


def test_the_template_gives_a_model_config_that_is_valid(tmp_path: Path) -> None:
    write_model_files(tmp_path, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    model = load_model_config(tmp_path).model

    assert model.name == "churn"
    assert model.flavor is Flavor.SKLEARN
    assert model.task is Task.BINARY_CLASSIFICATION
    assert model.entrypoint == "model.py:Churn"


@pytest.mark.parametrize(
    ("task", "estimator"),
    [
        (Task.BINARY_CLASSIFICATION, RandomForestClassifier),
        (Task.MULTICLASS_CLASSIFICATION, RandomForestClassifier),
        (Task.REGRESSION, RandomForestRegressor),
    ],
)
def test_the_generated_model_builds_a_pipeline_for_its_task(
    tmp_path: Path, task: Task, estimator: type
) -> None:
    write_model_files(tmp_path, "churn", "sklearn", task)

    pipeline = model_class(tmp_path)(task).build({"n_estimators": 300})

    assert isinstance(pipeline, Pipeline)
    assert [(name, type(step)) for name, step in pipeline.steps] == [
        ("scale", StandardScaler),
        ("model", estimator),
    ]
    assert pipeline.named_steps["model"].n_estimators == 300


@pytest.mark.parametrize("task", list(Task))
def test_the_generated_model_trains_and_predicts(tmp_path: Path, task: Task) -> None:
    write_model_files(tmp_path, "churn", "sklearn", task)
    model = model_class(tmp_path)(task)

    model.fit(DATA, "target", {"n_estimators": 5, "random_state": 0})

    assert model.predict(DATA).height == DATA.height


@pytest.mark.parametrize(
    ("name", "class_name"),
    [
        ("churn", "Churn"),
        ("churn-v2", "ChurnV2"),
        ("my-fraud-model", "MyFraudModel"),
        ("none", "NoneModel"),
        ("pipeline", "PipelineModel"),
        ("standard-scaler", "StandardScalerModel"),
        ("random-forest-classifier", "RandomForestClassifierModel"),
        ("sklearn-model", "SklearnModelModel"),
        ("sklearn", "Sklearn"),
    ],
)
def test_the_class_is_named_after_the_model_without_hiding_an_import(
    tmp_path: Path, name: str, class_name: str
) -> None:
    write_model_files(tmp_path, name, "sklearn", Task.BINARY_CLASSIFICATION)

    assert load_model_config(tmp_path).model.entrypoint == f"model.py:{class_name}"
    built = model_class(tmp_path)(Task.BINARY_CLASSIFICATION).build({})
    assert isinstance(built, Pipeline)


def test_the_files_are_the_same_on_every_system(tmp_path: Path) -> None:
    write_model_files(tmp_path, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".python-version",
        "model.py",
        "model.toml",
        "pyproject.toml",
    ]
    for path in tmp_path.iterdir():
        content = path.read_bytes()
        assert b"\r" not in content
        assert content.endswith(b"\n")
        assert not content.endswith(b"\n\n")


def test_the_environment_gets_this_miniops_and_this_python(tmp_path: Path) -> None:
    write_model_files(tmp_path, "churn", "sklearn", Task.REGRESSION)

    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    python = (tmp_path / ".python-version").read_text(encoding="utf-8")

    assert project["project"]["name"] == "churn"
    assert project["project"]["dependencies"] == [f"miniops-ml[sklearn]=={__version__}"]
    assert project["tool"]["uv"]["package"] is False
    assert python == f"{sys.version_info.major}.{sys.version_info.minor}\n"


class Installed:
    def __init__(self, direct_url: str | None) -> None:
        self.direct_url = direct_url

    def read_text(self, name: str) -> str | None:
        assert name == "direct_url.json"
        return self.direct_url


@pytest.mark.parametrize(
    ("direct_url", "source"),
    [
        (
            '{"url": "file:///D:/3.%20PROJEKTY/miniops", "dir_info": {"editable": true}}',
            {"path": "D:/3. PROJEKTY/miniops", "editable": True},
        ),
        (
            '{"url": "file:///home/patryk/mini%24ops", "dir_info": {}}',
            {"path": "/home/patryk/mini$ops", "editable": False},
        ),
        (
            '{"url": "file:///home/%F0%9F%98%80/miniops", "dir_info": {"editable": true}}',
            {"path": "/home/\U0001f600/miniops", "editable": True},
        ),
        (
            '{"url": "file://server/share/miniops", "dir_info": {"editable": true}}',
            {"path": "//server/share/miniops", "editable": True},
        ),
        (
            '{"url": "file://localhost/home/patryk/miniops", "dir_info": {"editable": true}}',
            {"path": "/home/patryk/miniops", "editable": True},
        ),
        (
            '{"url": "https://github.com/UltiPro/miniops.git",'
            ' "vcs_info": {"vcs": "git", "commit_id": "7bcaba2"}}',
            {"git": "https://github.com/UltiPro/miniops.git", "rev": "7bcaba2"},
        ),
        ('{"url": "https://hg.example.com/miniops", "vcs_info": {"vcs": "hg"}}', None),
        (
            '{"url": "file:///tmp/miniops_ml-0.1.0-py3-none-any.whl", "archive_info": {}}',
            {"path": "/tmp/miniops_ml-0.1.0-py3-none-any.whl"},
        ),
        (
            '{"url": "https://example.com/miniops_ml-0.1.0-py3-none-any.whl", "archive_info": {}}',
            {"url": "https://example.com/miniops_ml-0.1.0-py3-none-any.whl"},
        ),
        (None, None),
    ],
)
def test_the_environment_gets_miniops_from_where_this_one_came_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_url: str | None,
    source: dict[str, object] | None,
) -> None:
    monkeypatch.setattr(templates, "distribution", lambda name: Installed(direct_url))

    write_model_files(tmp_path, "churn", "sklearn", Task.REGRESSION)

    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["uv"].get("sources", {}).get("miniops-ml") == source


def test_a_miniops_that_is_not_installed_gives_no_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(name: str) -> Installed:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(templates, "distribution", missing)

    write_model_files(tmp_path, "churn", "sklearn", Task.REGRESSION)

    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert "sources" not in project["tool"]["uv"]


def test_a_flavor_without_a_template_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="no model template for the flavor 'keras'"):
        write_model_files(tmp_path, "churn", "keras", Task.BINARY_CLASSIFICATION)

    assert list(tmp_path.iterdir()) == []
