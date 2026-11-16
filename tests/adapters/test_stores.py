import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from miniops.adapters.stores import open_stores
from miniops.config.project import init_project
from miniops.core.entities import Model, Task

CONTENT = b"a trained model"
KEY = "runs/7c1e/model.skops"


def a_model() -> Model:
    return Model(
        id=uuid4(),
        name="churn",
        flavor="sklearn",
        task=Task.BINARY_CLASSIFICATION,
        created_at=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
    )


def a_file(directory: Path) -> Path:
    path = directory / "model.skops"
    path.write_bytes(CONTENT)
    return path


def test_the_stores_live_in_the_state_directory_of_the_project(tmp_path: Path) -> None:
    project = init_project(tmp_path)
    state = tmp_path / ".miniops"

    with open_stores(project) as stores:
        assert (state / "metadata.db").is_file()
        assert not (state / "artifacts").exists()
        stores.artifacts.put(a_file(tmp_path), KEY)

    assert (state / "artifacts" / "runs" / "7c1e" / "model.skops").is_file()


def test_what_was_stored_is_there_the_next_time(tmp_path: Path) -> None:
    project = init_project(tmp_path)
    model = a_model()
    with open_stores(project) as stores:
        stores.metadata.add_model(model)
        ref = stores.artifacts.put(a_file(tmp_path), KEY)

    with open_stores(project) as stores:
        assert stores.metadata.get_model("churn") == model
        stores.artifacts.get(ref, tmp_path / "copy.skops")

    assert (tmp_path / "copy.skops").read_bytes() == CONTENT


def test_the_metadata_store_is_closed_after_the_block(tmp_path: Path) -> None:
    with open_stores(init_project(tmp_path)) as stores:
        pass

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        stores.metadata.list_models()
