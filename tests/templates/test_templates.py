from pathlib import Path
from typing import Any

import polars as pl
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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

    assert sorted(path.name for path in tmp_path.iterdir()) == ["model.py", "model.toml"]
    for path in tmp_path.iterdir():
        assert b"\r" not in path.read_bytes()


def test_a_flavor_without_a_template_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="no model template for the flavor 'keras'"):
        write_model_files(tmp_path, "churn", "keras", Task.BINARY_CLASSIFICATION)

    assert list(tmp_path.iterdir()) == []
