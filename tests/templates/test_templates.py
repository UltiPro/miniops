import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from miniops.config.model import Flavor, load_model_config
from miniops.core.entities import Task
from miniops.core.errors import NotFoundError
from miniops.templates import write_model_files


class Step:
    def __init__(self, *args: Any, **params: Any) -> None:
        self.args = args
        self.params = params


def build_pipeline(directory: Path, monkeypatch: pytest.MonkeyPatch) -> Step:
    """Run the generated model with stand-ins for what it imports."""
    imports = {
        "sklearn": [],
        "sklearn.ensemble": ["RandomForestClassifier", "RandomForestRegressor"],
        "sklearn.pipeline": ["Pipeline"],
        "sklearn.preprocessing": ["StandardScaler"],
        "miniops.flavors": [],
        "miniops.flavors.sklearn": ["SklearnModel"],
    }
    for module_name, names in imports.items():
        module = ModuleType(module_name)
        for name in names:
            setattr(module, name, type(name, (Step,), {}))
        monkeypatch.setitem(sys.modules, module_name, module)

    file_name, class_name = load_model_config(directory).model.entrypoint.split(":")
    namespace: dict[str, type] = {}
    exec(compile((directory / file_name).read_text(encoding="utf-8"), file_name, "exec"), namespace)
    pipeline = namespace[class_name]().build({"n_estimators": 300})
    assert isinstance(pipeline, Step)
    return pipeline


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
        (Task.BINARY_CLASSIFICATION, "RandomForestClassifier"),
        (Task.MULTICLASS_CLASSIFICATION, "RandomForestClassifier"),
        (Task.REGRESSION, "RandomForestRegressor"),
    ],
)
def test_the_generated_model_builds_a_pipeline_for_its_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task: Task, estimator: str
) -> None:
    write_model_files(tmp_path, "churn", "sklearn", task)

    pipeline = build_pipeline(tmp_path, monkeypatch)

    assert type(pipeline).__name__ == "Pipeline"
    [(steps,)] = [pipeline.args]
    assert [(name, type(step).__name__) for name, step in steps] == [
        ("scale", "StandardScaler"),
        ("model", estimator),
    ]
    assert steps[1][1].params == {"n_estimators": 300}


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, class_name: str
) -> None:
    write_model_files(tmp_path, name, "sklearn", Task.BINARY_CLASSIFICATION)

    assert load_model_config(tmp_path).model.entrypoint == f"model.py:{class_name}"
    assert type(build_pipeline(tmp_path, monkeypatch)).__name__ == "Pipeline"


def test_the_files_are_the_same_on_every_system(tmp_path: Path) -> None:
    write_model_files(tmp_path, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["model.py", "model.toml"]
    for path in tmp_path.iterdir():
        assert b"\r" not in path.read_bytes()


def test_a_flavor_without_a_template_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError, match="no model template for the flavor 'keras'"):
        write_model_files(tmp_path, "churn", "keras", Task.BINARY_CLASSIFICATION)

    assert list(tmp_path.iterdir()) == []
