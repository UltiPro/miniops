import re
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from miniops.core.entities import Column, Signature, Task
from miniops.core.errors import DataError, InvalidStateError, UntrustedTypesError
from miniops.flavors.sklearn import SklearnModel

DATA = pl.DataFrame(
    {
        "age": [21, 35, 47, 52, 23, 61, 33, 44],
        "visits": [3.0, 1.5, None, 4.0, 2.5, 5.0, 1.0, 3.5],
        "churned": [0, 1, 0, 1, 0, 1, 0, 1],
        "plan": ["basic", "pro", "team", "basic", "pro", "team", "basic", "pro"],
        "revenue": [10.5, 30.0, 52.0, 12.5, 29.0, 55.5, 11.0, 31.5],
    }
)
TARGETS = {
    Task.BINARY_CLASSIFICATION: "churned",
    Task.MULTICLASS_CLASSIFICATION: "plan",
    Task.REGRESSION: "revenue",
}
PARAMS = {"n_estimators": 5, "random_state": 0}


class Forest(SklearnModel):
    def build(self, params: dict[str, Any]) -> Pipeline:
        model = RandomForestRegressor if self.task is Task.REGRESSION else RandomForestClassifier
        return Pipeline([("scale", StandardScaler()), ("model", model(**params))])


def trained(task: Task) -> tuple[Forest, Signature]:
    model = Forest(task)
    target = TARGETS[task]
    return model, model.fit(DATA.select("age", "visits", target), target, PARAMS)


@pytest.mark.parametrize(
    ("task", "dtype"),
    [
        (Task.BINARY_CLASSIFICATION, "Int64"),
        (Task.MULTICLASS_CLASSIFICATION, "String"),
        (Task.REGRESSION, "Float64"),
    ],
)
def test_a_model_learns_its_task_and_predicts_one_column(task: Task, dtype: str) -> None:
    model, signature = trained(task)

    prediction = model.predict(DATA)

    assert prediction.columns == ["prediction"]
    assert prediction.height == DATA.height
    assert str(prediction["prediction"].dtype) == dtype
    assert signature == Signature(
        inputs=(Column("age", "Int64"), Column("visits", "Float64", nullable=True)),
        outputs=(Column("prediction", dtype),),
    )


@pytest.mark.parametrize("task", list(Task))
def test_no_rows_give_an_empty_prediction_of_the_same_type(tmp_path: Path, task: Task) -> None:
    model, signature = trained(task)
    model.save(tmp_path)
    loaded = Forest.load(tmp_path, task, Forest.untrusted_types(tmp_path))

    for empty in (model.predict(DATA.clear()), loaded.predict(DATA.clear())):
        assert empty.height == 0
        assert str(empty["prediction"].dtype) == signature.outputs[0].dtype


def test_nan_is_an_empty_value_of_an_input() -> None:
    data = DATA.with_columns(visits=pl.Series([3.0, 1.5, float("nan"), 4.0, 2.5, 5.0, 1.0, 3.5]))

    signature = Forest(Task.REGRESSION).fit(data.select("age", "visits", "revenue"), "revenue", {})

    assert signature.inputs == (Column("age", "Int64"), Column("visits", "Float64", nullable=True))


def test_whole_numbers_in_a_column_of_floats_are_classes() -> None:
    data = DATA.with_columns(churned=pl.col("churned").cast(pl.Float64))

    signature = Forest(Task.BINARY_CLASSIFICATION).fit(data.select("age", "churned"), "churned", {})

    assert signature.outputs == (Column("prediction", "Float64"),)


def test_the_params_from_model_toml_reach_build() -> None:
    seen = []

    class Recording(Forest):
        def build(self, params: dict[str, Any]) -> Pipeline:
            seen.append(params)
            return super().build(params)

    Recording(Task.REGRESSION).fit(DATA.select("age", "revenue"), "revenue", PARAMS)

    assert seen == [PARAMS]


def test_a_column_that_the_model_was_trained_on_has_to_be_there() -> None:
    model, _ = trained(Task.REGRESSION)

    with pytest.raises(DataError, match=r"trained on columns that the data lacks: 'visits'\.$"):
        model.predict(DATA.drop("visits"))


@pytest.mark.parametrize(
    ("task", "data", "message"),
    [
        (Task.BINARY_CLASSIFICATION, DATA.drop("plan"), "no target column 'plan'"),
        (
            Task.BINARY_CLASSIFICATION,
            DATA.with_columns(plan=pl.Series([0, None, 1, 0, 1, None, 1, 0])),
            "'plan' is empty in 2 of 8 rows",
        ),
        (
            Task.BINARY_CLASSIFICATION,
            DATA,
            "A binary classification needs two classes in the target column 'plan', but it has 3",
        ),
        (
            Task.MULTICLASS_CLASSIFICATION,
            DATA.with_columns(plan=pl.lit("pro")),
            "A multiclass classification needs at least two classes in the target column 'plan', "
            "but it has 1",
        ),
        (
            Task.REGRESSION,
            DATA,
            "A regression needs numbers in the target column 'plan', but it holds String",
        ),
        (
            Task.BINARY_CLASSIFICATION,
            DATA.with_columns(plan=pl.Series([0.0, float("nan"), 1.0, 0.0, 1.0, 0.0, 1.0, 0.0])),
            "'plan' is empty in 1 of 8 rows",
        ),
        (
            Task.BINARY_CLASSIFICATION,
            DATA.with_columns(plan=pl.Series([0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0])),
            "needs classes in the target column 'plan', but it holds fractional numbers",
        ),
        (Task.REGRESSION, DATA.select("plan"), "no columns besides the target column 'plan'"),
        (Task.REGRESSION, DATA.clear(), "The data has no rows."),
    ],
)
def test_a_target_that_does_not_fit_the_task_is_refused(
    task: Task, data: pl.DataFrame, message: str
) -> None:
    with pytest.raises(DataError, match=message):
        Forest(task).fit(data, "plan", PARAMS)


def test_a_saved_model_predicts_the_same_after_loading(tmp_path: Path) -> None:
    model, _ = trained(Task.MULTICLASS_CLASSIFICATION)
    model.save(tmp_path)

    trusted = Forest.untrusted_types(tmp_path)
    loaded = Forest.load(tmp_path, Task.MULTICLASS_CLASSIFICATION, trusted)

    assert loaded.task is Task.MULTICLASS_CLASSIFICATION
    assert loaded.predict(DATA).equals(model.predict(DATA))
    assert [path.name for path in tmp_path.iterdir()] == ["model.skops"]


class Unchanged(TransformerMixin, BaseEstimator):  # type: ignore[misc]
    def fit(self, inputs: pl.DataFrame, labels: pl.Series | None = None) -> "Unchanged":
        return self

    def transform(self, inputs: pl.DataFrame) -> pl.DataFrame:
        return inputs


class WithOwnStep(SklearnModel):
    def build(self, params: dict[str, Any]) -> Pipeline:
        return Pipeline([("keep", Unchanged()), ("model", RandomForestClassifier(**params))])


def test_a_saved_model_with_a_type_that_is_not_trusted_is_not_loaded(tmp_path: Path) -> None:
    model = WithOwnStep(Task.BINARY_CLASSIFICATION)
    model.fit(DATA.select("age", "visits", "churned"), "churned", PARAMS)
    model.save(tmp_path)
    own = f"{Unchanged.__module__}.{Unchanged.__qualname__}"
    others = [name for name in WithOwnStep.untrusted_types(tmp_path) if name != own]

    with pytest.raises(UntrustedTypesError, match=re.escape(f"not trusted: {own}") + "$"):
        WithOwnStep.load(tmp_path, Task.BINARY_CLASSIFICATION, trusted=others)
    # A name given as a plain string is not read letter by letter as a match.
    with pytest.raises(UntrustedTypesError, match=re.escape(own)):
        WithOwnStep.load(tmp_path, Task.BINARY_CLASSIFICATION, trusted=own)


def test_an_untrained_model_can_neither_predict_nor_be_saved(tmp_path: Path) -> None:
    model = Forest(Task.REGRESSION)

    with pytest.raises(InvalidStateError, match="not trained"):
        model.predict(DATA)
    with pytest.raises(InvalidStateError, match="not trained"):
        model.save(tmp_path)


class Mean:
    def fit(self, inputs: pl.DataFrame, labels: pl.Series) -> "Mean":
        self.value = labels.mean()
        return self

    def predict(self, inputs: pl.DataFrame) -> np.ndarray:
        self.columns = inputs.columns
        return np.full(len(inputs), self.value)


class Average(SklearnModel):
    def build(self, params: dict[str, Any]) -> Mean:
        self.mean = Mean()
        return self.mean


def test_the_estimator_gets_only_its_inputs_in_their_order() -> None:
    model = Average(Task.REGRESSION)
    model.fit(DATA.select("age", "visits", "revenue"), "revenue", {})

    prediction = model.predict(DATA.select("revenue", "visits", "plan", "age"))

    assert prediction["prediction"].to_list() == [DATA["revenue"].mean()] * DATA.height
    assert model.mean.columns == ["age", "visits"]
