from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Self

import polars as pl

from miniops.core.entities import Json, Signature, Task
from miniops.flavors.base import FlavorModel


class Nothing(FlavorModel):
    def fit(self, data: pl.DataFrame, target: str, params: Mapping[str, Json]) -> Signature:
        return Signature(inputs=(), outputs=())

    def predict(self, data: pl.DataFrame) -> pl.DataFrame:
        return data

    def save(self, directory: Path) -> None:
        pass

    @classmethod
    def load(cls, directory: Path, task: Task, trusted: Collection[str] = ()) -> Self:
        return cls(task)


def test_a_flavor_whose_files_need_no_trust_names_no_types(tmp_path: Path) -> None:
    assert Nothing.untrusted_types(tmp_path) == []
