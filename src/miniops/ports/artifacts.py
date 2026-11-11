from pathlib import Path
from typing import Protocol

from miniops.core.entities import ArtifactRef


class ArtifactStore(Protocol):
    """Keeps files: model artifacts, reports and code snapshots.

    Keys are relative to the store and use "/", so the same key works on a disk and in a bucket.
    """

    def put(self, source: Path, key: str) -> ArtifactRef:
        """Copy a local file into the store and return its reference, digest included."""

    def get(self, ref: ArtifactRef, destination: Path) -> None:
        """Copy a stored file to a local path.

        Raises:
            NotFoundError: If the store has no file under this key.
            IntegrityError: If the stored content does not match the digest in the reference.
        """

    def exists(self, key: str) -> bool:
        """Tell whether the store has a file under this key."""

    def delete(self, key: str) -> None:
        """Remove a file. A missing key is not an error."""
