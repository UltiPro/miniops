import hashlib
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO, override
from uuid import uuid4

from miniops.core.entities import ArtifactRef, require_artifact_key
from miniops.core.errors import AlreadyExistsError, IntegrityError, NotFoundError
from miniops.ports.artifacts import ArtifactStore

_CHUNK = 1024 * 1024


class LocalArtifactStore(ArtifactStore):
    """The artifact store of the ``local`` and ``docker`` targets: files in one directory."""

    def __init__(self, root: Path) -> None:
        """Keep the files in ``root``. The directory is created with the first file."""
        self._root = root

    @override
    def put(self, source: Path, key: str) -> ArtifactRef:
        stored = self._path(key)
        if not stored.is_file():
            # Another command can take the key during the copy.
            with suppress(FileExistsError):
                with _atomic_write(stored, replace=False) as file:
                    digest, size = _read(source, copy_to=file)
                return ArtifactRef(key=key, digest=digest, size=size)
        digest, size = _read(source)
        if _read(stored) != (digest, size):
            raise AlreadyExistsError(
                f"The artifact store already has a different file under {key!r}."
            )
        return ArtifactRef(key=key, digest=digest, size=size)

    @override
    def get(self, ref: ArtifactRef, destination: Path) -> None:
        stored = self._path(ref.key)
        if not stored.is_file():
            raise NotFoundError(f"The artifact store has no file under {ref.key!r}.")
        with _atomic_write(destination, replace=True) as file:
            digest, _ = _read(stored, copy_to=file)
            if digest != ref.digest:
                raise IntegrityError(
                    f"{stored} does not match the digest recorded for it. "
                    "The file was changed or damaged after it was stored."
                )

    @override
    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    @override
    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        require_artifact_key(key)
        return self._root.joinpath(*key.split("/"))


def _read(path: Path, copy_to: BinaryIO | None = None) -> tuple[str, int]:
    """Return the SHA-256 digest and the size of a file, copying it on the way if asked."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
            if copy_to is not None:
                copy_to.write(chunk)
    return digest.hexdigest(), size


@contextmanager
def _atomic_write(target: Path, *, replace: bool) -> Generator[BinaryIO]:
    """Write a file that appears under its name only once it is complete.

    Raises:
        FileExistsError: If the name is taken and ``replace`` is off.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    # A key never starts with a dot, so this file is never taken for an artifact.
    unfinished = target.with_name(f".{target.name}.{uuid4().hex[:8]}.part")
    try:
        with unfinished.open("xb") as file:
            yield file
            file.flush()
            # Without this a power cut can leave an empty file under the real name.
            os.fsync(file.fileno())
        if replace:
            unfinished.replace(target)
        else:
            _rename_unless_taken(unfinished, target)
    finally:
        with suppress(OSError):
            unfinished.unlink()


def _rename_unless_taken(unfinished: Path, target: Path) -> None:
    try:
        # Unlike a rename, a hard link never replaces a file.
        target.hardlink_to(unfinished)
    except FileExistsError:
        raise
    except OSError:
        # No hard links here. Only Windows refuses a rename to a taken name.
        unfinished.rename(target)
