from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from miniops.adapters.local.artifacts import LocalArtifactStore
from miniops.adapters.local.metadata import SqliteMetadataStore, store_errors
from miniops.config.project import STATE_DIR, Project
from miniops.ports import ArtifactStore, MetadataStore


@dataclass(frozen=True)
class Stores:
    """The two stores of a project: the catalog and the files it points at."""

    metadata: MetadataStore
    artifacts: ArtifactStore


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
    database = state / "metadata.db"
    with store_errors(database), SqliteMetadataStore(database) as metadata:
        yield Stores(metadata=metadata, artifacts=LocalArtifactStore(state / "artifacts"))
