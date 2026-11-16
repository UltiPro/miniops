import hashlib
from pathlib import Path
from typing import BinaryIO

import pytest

from miniops.adapters.local import artifacts
from miniops.adapters.local.artifacts import LocalArtifactStore
from miniops.core.entities import ArtifactRef
from miniops.core.errors import AlreadyExistsError, IntegrityError, NotFoundError

CONTENT = b"a trained model"
KEY = "runs/7c1e/model.skops"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "artifacts"


@pytest.fixture
def store(root: Path) -> LocalArtifactStore:
    return LocalArtifactStore(root)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "model.skops"
    path.write_bytes(CONTENT)
    return path


def files_in(directory: Path) -> list[str]:
    return sorted(
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    )


def another_command_takes_the_key(
    content: bytes, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = artifacts._read

    def read_too_late(path: Path, copy_to: BinaryIO | None = None) -> tuple[str, int]:
        stored = root / "runs" / "7c1e" / "model.skops"
        if copy_to is not None and not stored.exists():
            stored.write_bytes(content)
        return read(path, copy_to)

    monkeypatch.setattr(artifacts, "_read", read_too_late)


def test_a_stored_file_gets_a_reference_with_its_digest_and_size(
    store: LocalArtifactStore, root: Path, source: Path
) -> None:
    ref = store.put(source, KEY)

    assert ref == ArtifactRef(
        key=KEY, digest=hashlib.sha256(CONTENT).hexdigest(), size=len(CONTENT)
    )
    assert files_in(root) == [KEY]
    assert (root / "runs" / "7c1e" / "model.skops").read_bytes() == CONTENT


def test_a_file_comes_back_as_it_was_stored(
    store: LocalArtifactStore, source: Path, tmp_path: Path
) -> None:
    ref = store.put(source, KEY)
    copy = tmp_path / "work" / "model.skops"

    store.get(ref, copy)

    assert files_in(tmp_path / "work") == ["model.skops"]
    assert copy.read_bytes() == CONTENT


def test_get_replaces_a_file_that_is_already_there(
    store: LocalArtifactStore, source: Path, tmp_path: Path
) -> None:
    ref = store.put(source, KEY)
    copy = tmp_path / "copy.skops"
    copy.write_bytes(b"an older model")

    store.get(ref, copy)

    assert copy.read_bytes() == CONTENT


def test_a_file_read_in_several_pieces_keeps_its_digest(
    store: LocalArtifactStore, source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts, "_CHUNK", 4)

    ref = store.put(source, KEY)
    store.get(ref, tmp_path / "copy.skops")

    assert ref.digest == hashlib.sha256(CONTENT).hexdigest()
    assert ref.size == len(CONTENT)
    assert (tmp_path / "copy.skops").read_bytes() == CONTENT


def test_an_empty_file_can_be_stored(store: LocalArtifactStore, tmp_path: Path) -> None:
    empty = tmp_path / "train.log"
    empty.touch()

    ref = store.put(empty, "runs/7c1e/train.log")
    store.get(ref, tmp_path / "copy.log")

    assert ref.size == 0
    assert ref.digest == hashlib.sha256(b"").hexdigest()
    assert (tmp_path / "copy.log").read_bytes() == b""


def test_the_same_file_can_be_put_again(
    store: LocalArtifactStore, root: Path, source: Path
) -> None:
    first = store.put(source, KEY)

    assert store.put(source, KEY) == first
    assert files_in(root) == [KEY]


def test_a_stored_file_is_never_replaced(
    store: LocalArtifactStore, root: Path, source: Path, tmp_path: Path
) -> None:
    store.put(source, KEY)
    other = tmp_path / "other.skops"
    other.write_bytes(b"another model")

    with pytest.raises(AlreadyExistsError, match="already has a different file"):
        store.put(other, KEY)

    assert files_in(root) == [KEY]
    assert (root / "runs" / "7c1e" / "model.skops").read_bytes() == CONTENT


def test_a_key_taken_while_copying_is_not_replaced(
    store: LocalArtifactStore, root: Path, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    another_command_takes_the_key(b"another model", root, monkeypatch)

    with pytest.raises(AlreadyExistsError, match="already has a different file"):
        store.put(source, KEY)

    assert files_in(root) == [KEY]
    assert (root / "runs" / "7c1e" / "model.skops").read_bytes() == b"another model"


def test_the_same_file_stored_while_copying_is_fine(
    store: LocalArtifactStore, root: Path, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    another_command_takes_the_key(CONTENT, root, monkeypatch)

    ref = store.put(source, KEY)

    assert ref.digest == hashlib.sha256(CONTENT).hexdigest()
    assert files_in(root) == [KEY]


def test_a_file_is_stored_on_a_file_system_without_hard_links(
    store: LocalArtifactStore, root: Path, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object) -> None:
        raise OSError("This file system has no hard links")

    monkeypatch.setattr(Path, "hardlink_to", refuse)

    store.put(source, KEY)

    assert files_in(root) == [KEY]
    assert (root / "runs" / "7c1e" / "model.skops").read_bytes() == CONTENT


def test_a_put_that_fails_leaves_no_file_behind(
    store: LocalArtifactStore, root: Path, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        store.put(tmp_path / "missing.skops", KEY)

    assert files_in(root) == []
    assert not store.exists(KEY)


def test_a_key_that_is_not_in_the_store_is_not_found(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    ref = ArtifactRef(key=KEY, digest="a" * 64, size=1)

    with pytest.raises(NotFoundError, match="has no file under"):
        store.get(ref, tmp_path / "copy.skops")

    assert not (tmp_path / "copy.skops").exists()


def test_a_damaged_file_is_not_handed_out(
    store: LocalArtifactStore, root: Path, source: Path, tmp_path: Path
) -> None:
    ref = store.put(source, KEY)
    copy = tmp_path / "work" / "model.skops"
    store.get(ref, copy)
    (root / "runs" / "7c1e" / "model.skops").write_bytes(b"something else")

    with pytest.raises(IntegrityError, match="does not match the digest"):
        store.get(ref, copy)

    assert files_in(tmp_path / "work") == ["model.skops"]
    assert copy.read_bytes() == CONTENT


def test_exists_is_true_only_for_a_stored_file(store: LocalArtifactStore, source: Path) -> None:
    assert not store.exists(KEY)

    store.put(source, KEY)

    assert store.exists(KEY)
    assert not store.exists("runs/7c1e")


def test_delete_removes_a_file_and_does_not_mind_a_missing_one(
    store: LocalArtifactStore, source: Path
) -> None:
    store.put(source, KEY)

    store.delete(KEY)
    store.delete(KEY)

    assert not store.exists(KEY)


@pytest.mark.parametrize(
    "key",
    [
        "../outside.skops",
        "/outside.skops",
        "runs/../../outside.skops",
        "runs\\outside.skops",
        "Runs/model.skops",
        ".hidden",
    ],
)
def test_a_key_that_is_not_valid_touches_nothing(
    store: LocalArtifactStore, source: Path, tmp_path: Path, key: str
) -> None:
    with pytest.raises(ValueError, match="artifact key"):
        store.put(source, key)
    with pytest.raises(ValueError, match="artifact key"):
        store.exists(key)
    with pytest.raises(ValueError, match="artifact key"):
        store.delete(key)

    assert files_in(tmp_path) == ["model.skops"]


def test_nothing_is_created_before_the_first_file(store: LocalArtifactStore, root: Path) -> None:
    assert not store.exists(KEY)
    store.delete(KEY)

    assert not root.exists()
