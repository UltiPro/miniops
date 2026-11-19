from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from miniops.adapters.local.artifacts import LocalArtifactStore
from miniops.adapters.local.metadata import SqliteMetadataStore, store_errors
from miniops.adapters.local.schema import newest_version, read_version
from miniops.config.project import STATE_DIR, Project
from miniops.ports import ArtifactStore, MetadataStore

_METADATA_FILE = "metadata.db"


@dataclass(frozen=True)
class Stores:
    """The two stores of a project: the catalog and the files it points at."""

    metadata: MetadataStore
    artifacts: ArtifactStore


@dataclass(frozen=True)
class StoreSchema:
    """The schema version of a metadata store, and the newest one that this miniOPs knows."""

    version: int | None
    newest: int


@contextmanager
def open_stores(project: Project) -> Generator[Stores]:
    """Open the stores of a project and close them at the end of the block.

    They live in ``.miniops/`` in the project directory and are created on first use.

    Raises:
        IncompatibleStoreError: If the metadata store was written by a newer miniOPs.
        StoreBusyError: If another process is using the metadata store, also later in the
            block.
        OSError: If the disk or the file of the metadata store fails, also later in the block.
    """
    state = project.root / STATE_DIR
    database = state / _METADATA_FILE
    with store_errors(database), SqliteMetadataStore(database) as metadata:
        yield Stores(metadata=metadata, artifacts=LocalArtifactStore(state / "artifacts"))


def store_schema(project: Project) -> StoreSchema:
    """Read the schema version of the metadata store of a project.

    The version is None while the store does not exist. Nothing is created or upgraded.

    Raises:
        StoreBusyError: If another process is using the metadata store.
        OSError: If the disk or the file of the metadata store fails.
    """
    state = project.root / STATE_DIR
    if state.exists() and not state.is_dir():
        raise OSError(f"{state} is not a directory, so the stores cannot be created in it.")
    database = state / _METADATA_FILE
    with store_errors(database):
        version = read_version(database)
    return StoreSchema(version=version, newest=newest_version())
