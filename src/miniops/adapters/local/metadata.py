import json
import sqlite3
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, override
from uuid import UUID

from miniops.adapters.local.schema import migrate
from miniops.core.entities import (
    Alias,
    ArtifactRef,
    Column,
    DatasetRef,
    Model,
    ModelVersion,
    Run,
    RunStatus,
    Signature,
    VersionRef,
    VersionStatus,
)
from miniops.core.errors import AlreadyExistsError, InvalidStateError, NotFoundError
from miniops.core.versions import SemVer
from miniops.ports.metadata import MetadataStore


class SqliteMetadataStore(MetadataStore):
    """The metadata store of the ``local`` and ``docker`` targets: one SQLite file."""

    def __init__(self, path: Path) -> None:
        """Open the store at ``path``. A missing store is created and an older one is upgraded.

        Raises:
            IncompatibleStoreError: If the store was written by a newer miniOPs.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, autocommit=True)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            migrate(self._connection, path)
        except BaseException:
            self._connection.close()
            raise

    def close(self) -> None:
        """Close the database file."""
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @override
    def add_model(self, model: Model) -> None:
        with _constraints(taken=f"Model {model.name!r} is already in the store."):
            self._connection.execute(*_insert("models", _model_row(model)))

    @override
    def get_model(self, name: str) -> Model | None:
        row = self._connection.execute("SELECT * FROM models WHERE name = ?", (name,)).fetchone()
        return _maybe(row, _model)

    @override
    def list_models(self) -> Sequence[Model]:
        rows = self._connection.execute("SELECT * FROM models ORDER BY name")
        return [_model(row) for row in rows]

    @override
    def add_version(self, version: ModelVersion) -> None:
        if version.status is not VersionStatus.DRAFT:
            raise InvalidStateError(
                f"Version {version.number} is {version.status}. A version enters the store "
                "as a draft and is released there."
            )
        with _constraints(
            taken=f"The model already has a version {version.number}.",
            missing=f"The store has no model with id {version.model_id}.",
        ):
            self._connection.execute(*_insert("versions", _version_row(version)))

    @override
    def update_version(self, version: ModelVersion) -> None:
        with _constraints(
            taken=f"The model already has a version {version.number}.",
            missing=f"Run {version.released_run_id} is not a run of version {version.number}.",
        ):
            updated = self._connection.execute(*_update("versions", _version_row(version)))
        if updated.rowcount == 0:
            raise NotFoundError(f"The store has no version with id {version.id}.")

    @override
    def delete_version(self, version_id: UUID) -> None:
        deleted = self._connection.execute(
            "DELETE FROM versions WHERE id = ? AND status = 'draft'", (str(version_id),)
        )
        if deleted.rowcount:
            return
        row = self._connection.execute(
            "SELECT number, status FROM versions WHERE id = ?", (str(version_id),)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"The store has no version with id {version_id}.")
        raise InvalidStateError(
            f"Version {row['number']} is {row['status']}, only a draft can be removed."
        )

    @override
    def get_version(self, model_id: UUID, number: SemVer) -> ModelVersion | None:
        row = self._connection.execute(
            "SELECT * FROM versions WHERE model_id = ? AND number = ?", (str(model_id), str(number))
        ).fetchone()
        return _maybe(row, _version)

    @override
    def list_versions(self, model_id: UUID) -> Sequence[ModelVersion]:
        rows = self._connection.execute(
            "SELECT * FROM versions WHERE model_id = ?", (str(model_id),)
        )
        # Numbers are stored as text, and "1.10.0" sorts before "1.2.0" there.
        versions = [_version(row) for row in rows]
        return sorted(versions, key=lambda version: version.number, reverse=True)

    @override
    def add_run(self, run: Run) -> None:
        with _constraints(
            taken=f"Run {run.id} is already in the store.",
            missing=f"Run {run.id} belongs to a version or a parent run that is not in the store.",
        ):
            self._connection.execute(*_insert("runs", _run_row(run)))

    @override
    def update_run(self, run: Run) -> None:
        with _constraints(
            missing=f"Run {run.id} belongs to a version or a parent run that is not in the store."
        ):
            updated = self._connection.execute(*_update("runs", _run_row(run)))
        if updated.rowcount == 0:
            raise NotFoundError(f"The store has no run with id {run.id}.")

    @override
    def get_run(self, run_id: UUID) -> Run | None:
        row = self._connection.execute("SELECT * FROM runs WHERE id = ?", (str(run_id),)).fetchone()
        return _maybe(row, _run)

    @override
    def list_runs(self, version_id: UUID) -> Sequence[Run]:
        rows = self._connection.execute(
            "SELECT * FROM runs WHERE version_id = ? ORDER BY started_at, rowid", (str(version_id),)
        )
        return [_run(row) for row in rows]

    @override
    def set_alias(self, alias: Alias) -> None:
        sql, row = _insert("aliases", _alias_row(alias))
        with _constraints(missing=f"The model has no version with id {alias.version_id}."):
            self._connection.execute(
                f"{sql} ON CONFLICT (model_id, name) DO UPDATE SET "
                "version_id = excluded.version_id, updated_at = excluded.updated_at",
                row,
            )

    @override
    def delete_alias(self, model_id: UUID, name: str) -> None:
        deleted = self._connection.execute(
            "DELETE FROM aliases WHERE model_id = ? AND name = ?", (str(model_id), name)
        )
        if deleted.rowcount == 0:
            raise NotFoundError(f"The model has no alias {name!r}.")

    @override
    def get_alias(self, model_id: UUID, name: str) -> Alias | None:
        row = self._connection.execute(
            "SELECT * FROM aliases WHERE model_id = ? AND name = ?", (str(model_id), name)
        ).fetchone()
        return _maybe(row, _alias)

    @override
    def list_aliases(self, model_id: UUID) -> Sequence[Alias]:
        rows = self._connection.execute(
            "SELECT * FROM aliases WHERE model_id = ? ORDER BY name", (str(model_id),)
        )
        return [_alias(row) for row in rows]


type _Row = Mapping[str, object]


@contextmanager
def _constraints(*, taken: str | None = None, missing: str | None = None) -> Generator[None]:
    """Turn a broken database constraint into the error that the port promises."""
    try:
        yield
    except sqlite3.IntegrityError as error:
        kind = error.sqlite_errorname
        if taken and kind in ("SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY"):
            raise AlreadyExistsError(taken) from error
        if missing and kind == "SQLITE_CONSTRAINT_FOREIGNKEY":
            raise NotFoundError(missing) from error
        raise


def _insert(table: str, row: _Row) -> tuple[str, _Row]:
    columns = ", ".join(row)
    values = ", ".join(f":{column}" for column in row)
    return f"INSERT INTO {table} ({columns}) VALUES ({values})", row


def _update(table: str, row: _Row) -> tuple[str, _Row]:
    changes = ", ".join(f"{column} = :{column}" for column in row if column != "id")
    return f"UPDATE {table} SET {changes} WHERE id = :id", row


def _maybe[T, R](value: T | None, convert: Callable[[T], R]) -> R | None:
    return None if value is None else convert(value)


def _text(moment: datetime) -> str:
    # Always UTC and always the same width, so sorting the text sorts by time.
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _model_row(model: Model) -> _Row:
    return {
        "id": str(model.id),
        "name": model.name,
        "flavor": model.flavor,
        "task": model.task,
        "created_at": _text(model.created_at),
    }


def _model(row: sqlite3.Row) -> Model:
    return Model(
        id=UUID(row["id"]),
        name=row["name"],
        flavor=row["flavor"],
        task=row["task"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _version_row(version: ModelVersion) -> _Row:
    return {
        "id": str(version.id),
        "model_id": str(version.model_id),
        "number": str(version.number),
        "status": str(version.status),
        "base_number": _maybe(version.base, lambda base: str(base.number)),
        "base_digest": _maybe(version.base, lambda base: base.digest),
        "released_run_id": _maybe(version.released_run_id, str),
        "content_digest": version.content_digest,
        "released_at": _maybe(version.released_at, _text),
        "created_at": _text(version.created_at),
    }


def _version(row: sqlite3.Row) -> ModelVersion:
    base = None
    if row["base_number"] is not None:
        base = VersionRef(number=SemVer.parse(row["base_number"]), digest=row["base_digest"])
    return ModelVersion(
        id=UUID(row["id"]),
        model_id=UUID(row["model_id"]),
        number=SemVer.parse(row["number"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        status=VersionStatus(row["status"]),
        base=base,
        released_run_id=_maybe(row["released_run_id"], UUID),
        content_digest=row["content_digest"],
        released_at=_maybe(row["released_at"], datetime.fromisoformat),
    )


def _run_row(run: Run) -> _Row:
    return {
        "id": str(run.id),
        "version_id": str(run.version_id),
        "parent_run_id": _maybe(run.parent_run_id, str),
        "status": str(run.status),
        "started_at": _text(run.started_at),
        "finished_at": _maybe(run.finished_at, _text),
        "miniops_version": run.miniops_version,
        "params": json.dumps(dict(run.params)),
        "metrics": json.dumps(dict(run.metrics)),
        "dataset_uri": _maybe(run.dataset, lambda dataset: dataset.uri),
        "dataset_fingerprint": _maybe(run.dataset, lambda dataset: dataset.fingerprint),
        **_artifact_row("snapshot", run.snapshot),
        "lock_digest": run.lock_digest,
        "code_commit": run.code_commit,
        **_artifact_row("artifact", run.artifact),
        "signature": _maybe(run.signature, lambda signature: json.dumps(asdict(signature))),
        "error": run.error,
    }


def _run(row: sqlite3.Row) -> Run:
    dataset = None
    if row["dataset_uri"] is not None:
        dataset = DatasetRef(uri=row["dataset_uri"], fingerprint=row["dataset_fingerprint"])
    return Run(
        id=UUID(row["id"]),
        version_id=UUID(row["version_id"]),
        parent_run_id=_maybe(row["parent_run_id"], UUID),
        status=RunStatus(row["status"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=_maybe(row["finished_at"], datetime.fromisoformat),
        miniops_version=row["miniops_version"],
        params=json.loads(row["params"]),
        metrics=json.loads(row["metrics"]),
        dataset=dataset,
        snapshot=_artifact(row, "snapshot"),
        lock_digest=row["lock_digest"],
        code_commit=row["code_commit"],
        artifact=_artifact(row, "artifact"),
        signature=_maybe(row["signature"], _signature),
        error=row["error"],
    )


def _artifact_row(prefix: str, ref: ArtifactRef | None) -> _Row:
    key, digest, size = (None, None, None) if ref is None else (ref.key, ref.digest, ref.size)
    return {f"{prefix}_key": key, f"{prefix}_digest": digest, f"{prefix}_size": size}


def _artifact(row: sqlite3.Row, prefix: str) -> ArtifactRef | None:
    if row[f"{prefix}_key"] is None:
        return None
    return ArtifactRef(
        key=row[f"{prefix}_key"], digest=row[f"{prefix}_digest"], size=row[f"{prefix}_size"]
    )


def _signature(text: str) -> Signature:
    columns = json.loads(text)
    return Signature(
        inputs=tuple(Column(**column) for column in columns["inputs"]),
        outputs=tuple(Column(**column) for column in columns["outputs"]),
    )


def _alias_row(alias: Alias) -> _Row:
    return {
        "model_id": str(alias.model_id),
        "name": alias.name,
        "version_id": str(alias.version_id),
        "updated_at": _text(alias.updated_at),
    }


def _alias(row: sqlite3.Row) -> Alias:
    return Alias(
        model_id=UUID(row["model_id"]),
        name=row["name"],
        version_id=UUID(row["version_id"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
