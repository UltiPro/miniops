import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from miniops.core.errors import IncompatibleStoreError

logger = logging.getLogger(__name__)

# A released script never changes: a change to the schema is a new script at the end.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE models (
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        flavor TEXT NOT NULL,
        task TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE versions (
        id TEXT NOT NULL PRIMARY KEY,
        model_id TEXT NOT NULL REFERENCES models (id),
        number TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('draft', 'released', 'deleted')),
        base_number TEXT,
        base_digest TEXT,
        released_run_id TEXT,
        content_digest TEXT,
        released_at TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (model_id, number),
        UNIQUE (model_id, id),
        FOREIGN KEY (id, released_run_id) REFERENCES runs (version_id, id)
    );

    CREATE TABLE runs (
        id TEXT NOT NULL PRIMARY KEY,
        version_id TEXT NOT NULL REFERENCES versions (id) ON DELETE CASCADE,
        parent_run_id TEXT REFERENCES runs (id),
        status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'interrupted')),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        miniops_version TEXT NOT NULL,
        params TEXT NOT NULL,
        metrics TEXT NOT NULL,
        dataset_uri TEXT,
        dataset_fingerprint TEXT,
        snapshot_key TEXT,
        snapshot_digest TEXT,
        snapshot_size INTEGER,
        lock_digest TEXT,
        code_commit TEXT,
        artifact_key TEXT,
        artifact_digest TEXT,
        artifact_size INTEGER,
        signature TEXT,
        error TEXT,
        UNIQUE (version_id, id)
    );

    CREATE TABLE aliases (
        model_id TEXT NOT NULL,
        name TEXT NOT NULL,
        version_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (model_id, name),
        FOREIGN KEY (model_id, version_id) REFERENCES versions (model_id, id)
    );
    """,
)


def schema_version(connection: sqlite3.Connection) -> int:
    """Return the schema version of a store. An empty database has version 0."""
    version: int = connection.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(connection: sqlite3.Connection, path: Path) -> None:
    """Bring a store up to the newest schema, after saving a copy of an older one.

    Raises:
        IncompatibleStoreError: If the store was written by a newer miniOPs.
    """
    version = schema_version(connection)
    newest = len(MIGRATIONS)
    if version > newest:
        raise IncompatibleStoreError(
            f"The store at {path} has schema version {version}, but this miniOPs reads "
            f"up to version {newest}. Upgrade miniOPs to use this store."
        )
    if version == newest:
        return
    if version > 0:
        _back_up(connection, path, version)

    connection.execute("BEGIN IMMEDIATE")
    try:
        # Read the version again: another process may have upgraded the store in the meantime.
        for number in range(schema_version(connection), newest):
            connection.executescript(MIGRATIONS[number])
            connection.execute(f"PRAGMA user_version = {number + 1}")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    logger.info("The store %s now has schema version %d", path, newest)


def _back_up(connection: sqlite3.Connection, path: Path, version: int) -> None:
    backup = path.with_name(f"{path.name}.v{version}.bak")
    with closing(sqlite3.connect(backup)) as copy:
        connection.backup(copy)
    logger.info("Copied the store %s to %s before upgrading its schema", path, backup)
