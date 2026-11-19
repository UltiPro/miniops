from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Self

import polars as pl

from miniops.core.entities import Column, Json, Signature, Task
from miniops.core.errors import DataError


class FlavorModel(ABC):
    """The base of every model class: what miniOPs asks of a model, whatever its framework."""

    def __init__(self, task: Task) -> None:
        """Make an untrained model for ``task``."""
        self.task = task

    @abstractmethod
    def fit(self, data: pl.DataFrame, target: str, params: Mapping[str, Json]) -> Signature:
        """Train on ``data`` to predict its column ``target``, and return the signature.

        Every other column of ``data`` is an input of the model.

        Raises:
            DataError: If the data has no rows or no inputs, or the target column is missing,
                has empty values or does not fit the task.
        """

    @abstractmethod
    def predict(self, data: pl.DataFrame) -> pl.DataFrame:
        """Return one ``prediction`` for every row of ``data``, also for no rows.

        Columns that the model was not trained on are left out.

        Raises:
            DataError: If a column that the model was trained on is missing.
            InvalidStateError: If the model is not trained.
        """

    @abstractmethod
    def save(self, directory: Path) -> None:
        """Write the trained model into ``directory``.

        Raises:
            InvalidStateError: If the model is not trained.
        """

    @classmethod
    @abstractmethod
    def load(cls, directory: Path, task: Task, trusted: Collection[str] = ()) -> Self:
        """Read a model that ``save`` wrote into ``directory``.

        Raises:
            UntrustedTypesError: If the files need a type that is not in ``trusted``.
        """

    @classmethod
    def untrusted_types(cls, directory: Path) -> list[str]:
        """Return the types that loading the model in ``directory`` has to trust."""
        return []


def split_target(data: pl.DataFrame, target: str, task: Task) -> tuple[pl.DataFrame, pl.Series]:
    """Split ``data`` into the inputs and the column that a model for ``task`` learns to predict.

    Raises:
        DataError: If the data has no rows or no inputs, or the target column is missing, has
            empty values or does not fit the task.
    """
    if target not in data.columns:
        raise DataError(f"The data has no target column {target!r}.")
    if data.width == 1:
        raise DataError(f"The data has no columns besides the target column {target!r}.")
    if data.height == 0:
        raise DataError("The data has no rows.")
    labels = data[target]
    if empty := _empty(labels):
        raise DataError(f"The target column {target!r} is empty in {empty} of {len(labels)} rows.")
    if task is Task.REGRESSION:
        if not labels.dtype.is_numeric():
            raise DataError(
                f"A regression needs numbers in the target column {target!r}, "
                f"but it holds {labels.dtype}."
            )
        return data.drop(target), labels
    if labels.dtype.is_float() and (labels != labels.round()).any():
        raise DataError(
            f"A classification needs classes in the target column {target!r}, "
            "but it holds fractional numbers."
        )
    classes = labels.n_unique()
    if task is Task.BINARY_CLASSIFICATION and classes != 2:
        raise DataError(
            f"A binary classification needs two classes in the target column {target!r}, "
            f"but it has {classes}."
        )
    if classes < 2:
        raise DataError(
            f"A multiclass classification needs at least two classes in the target column "
            f"{target!r}, but it has {classes}."
        )
    return data.drop(target), labels


def signature_of(inputs: pl.DataFrame, prediction: pl.Series) -> Signature:
    """Describe the inputs a model was trained on and the prediction it gives."""
    return Signature(
        inputs=tuple(
            Column(name, str(dtype), nullable=_empty(inputs[name]) > 0)
            for name, dtype in inputs.schema.items()
        ),
        outputs=(Column(prediction.name, str(prediction.dtype)),),
    )


def _empty(values: pl.Series) -> int:
    # polars keeps NaN apart from null, but to a model both are a missing value.
    nan = int(values.is_nan().sum()) if values.dtype.is_float() else 0
    return values.null_count() + nan
