import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from miniops.adapters.local import schema
from miniops.adapters.local.metadata import SqliteMetadataStore
from miniops.core.entities import Model
from miniops.core.errors import IncompatibleStoreError

MODEL = Model(
    id=uuid4(),
    name="churn",
    flavor="sklearn",
    task="binary_classification",
    created_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC),
)


def version_of(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        return schema.schema_version(connection)


def tables_of(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def test_a_new_store_gets_the_newest_schema(tmp_path: Path) -> None:
    path = tmp_path / "metadata.db"

    SqliteMetadataStore(path).close()

    assert version_of(path) == len(schema.MIGRATIONS)
    assert tables_of(path) == {"models", "versions", "runs", "aliases"}
    assert list(tmp_path.iterdir()) == [path]


def test_an_older_store_is_upgraded_after_a_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "metadata.db"
    with SqliteMetadataStore(path) as store:
        store.add_model(MODEL)
    older = len(schema.MIGRATIONS)
    monkeypatch.setattr(
        schema, "MIGRATIONS", (*schema.MIGRATIONS, "CREATE TABLE deployments (id TEXT);")
    )

    with SqliteMetadataStore(path) as store:
        assert store.list_models() == [MODEL]

    backup = tmp_path / f"metadata.db.v{older}.bak"
    assert version_of(path) == older + 1
    assert "deployments" in tables_of(path)
    assert version_of(backup) == older
    assert "deployments" not in tables_of(backup)
    with SqliteMetadataStore(backup) as store:
        assert store.list_models() == [MODEL]


def test_a_failed_upgrade_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "metadata.db"
    with SqliteMetadataStore(path) as store:
        store.add_model(MODEL)
    older = len(schema.MIGRATIONS)
    broken = "CREATE TABLE deployments (id TEXT); CREATE TABLE models (id TEXT);"
    monkeypatch.setattr(schema, "MIGRATIONS", (*schema.MIGRATIONS, broken))

    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        SqliteMetadataStore(path)

    assert version_of(path) == older
    assert "deployments" not in tables_of(path)


def test_a_store_from_a_newer_miniops_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "metadata.db"
    SqliteMetadataStore(path).close()
    newer = len(schema.MIGRATIONS) + 1
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(f"PRAGMA user_version = {newer}")

    with pytest.raises(IncompatibleStoreError, match="Upgrade miniOPs"):
        SqliteMetadataStore(path)

    # Windows refuses to delete a file that is still open, so this also proves it was closed.
    path.unlink()
