from abc import abstractmethod
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, Self, override

import polars as pl
import skops.io

from miniops.core.entities import Json, Signature, Task
from miniops.core.errors import DataError, InvalidStateError, UntrustedTypesError
from miniops.flavors.base import FlavorModel, signature_of, split_target

_FILE = "model.skops"
_PREDICTION = "prediction"


class SklearnModel(FlavorModel):
    """The base of a scikit-learn model. ``build`` returns its estimator, usually a ``Pipeline``.

    The model is saved with skops, which refuses to load a type that was not trusted, where
    pickle would run any code that the file holds.
    """

    def __init__(self, task: Task) -> None:
        """Make an untrained model for ``task``."""
        super().__init__(task)
        self._estimator: Any = None
        self._inputs: list[str] = []
        # One prediction made at training, so that no rows still give a column of its type.
        self._sample: Any = None

    @abstractmethod
    def build(self, params: dict[str, Any]) -> Any:
        """Return a new, untrained estimator made with ``params`` from ``model.toml``."""

    @override
    def fit(self, data: pl.DataFrame, target: str, params: Mapping[str, Json]) -> Signature:
        inputs, labels = split_target(data, target, self.task)
        estimator = self.build(dict(params))
        estimator.fit(inputs, labels)
        self._estimator = estimator
        self._inputs = inputs.columns
        self._sample = estimator.predict(inputs.head(1))
        return signature_of(inputs, pl.Series(_PREDICTION, self._sample))

    @override
    def predict(self, data: pl.DataFrame) -> pl.DataFrame:
        estimator = self._trained()
        missing = [name for name in self._inputs if name not in data.columns]
        if missing:
            raise DataError(
                "The model was trained on columns that the data lacks: "
                f"{', '.join(map(repr, missing))}."
            )
        if data.height == 0:
            return pl.Series(_PREDICTION, self._sample).clear().to_frame()
        return pl.Series(_PREDICTION, estimator.predict(data.select(self._inputs))).to_frame()

    @override
    def save(self, directory: Path) -> None:
        saved = {"estimator": self._trained(), "inputs": self._inputs, "sample": self._sample}
        skops.io.dump(saved, directory / _FILE)

    @override
    @classmethod
    def load(cls, directory: Path, task: Task, trusted: Collection[str] = ()) -> Self:
        path = directory / _FILE
        allowed = set(trusted)
        refused = [name for name in cls.untrusted_types(directory) if name not in allowed]
        if refused:
            raise UntrustedTypesError(
                f"{path} uses types that are not trusted: {', '.join(refused)}"
            )
        saved = skops.io.load(path, trusted=sorted(allowed))
        model = cls(task)
        model._estimator, model._inputs, model._sample = (
            saved["estimator"],
            saved["inputs"],
            saved["sample"],
        )
        return model

    @override
    @classmethod
    def untrusted_types(cls, directory: Path) -> list[str]:
        types: list[str] = skops.io.get_untrusted_types(file=directory / _FILE)
        return types

    def _trained(self) -> Any:
        if self._estimator is None:
            raise InvalidStateError("The model is not trained. Call fit or load first.")
        return self._estimator
