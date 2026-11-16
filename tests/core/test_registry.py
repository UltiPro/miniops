from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from miniops.adapters.local.metadata import SqliteMetadataStore
from miniops.config.model import load_model_config
from miniops.core.entities import Task, VersionStatus
from miniops.core.errors import AlreadyExistsError, NotFoundError
from miniops.core.registry import create_model
from miniops.core.versions import FIRST_VERSION


@pytest.fixture
def metadata(tmp_path: Path) -> Iterator[SqliteMetadataStore]:
    with SqliteMetadataStore(tmp_path / ".miniops" / "metadata.db") as store:
        yield store


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    return tmp_path / "models" / "churn"


def test_a_new_model_gets_a_directory_and_a_first_draft(
    metadata: SqliteMetadataStore, directory: Path
) -> None:
    draft = create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    model = metadata.get_model("churn")
    assert model is not None
    assert model.flavor == "sklearn"
    assert model.task is Task.BINARY_CLASSIFICATION
    assert metadata.list_versions(model.id) == [draft]
    assert draft.number == FIRST_VERSION
    assert draft.status is VersionStatus.DRAFT
    assert draft.base is None
    assert load_model_config(directory).model.name == "churn"
    assert (directory / "model.py").is_file()


def test_a_model_name_is_used_once(
    metadata: SqliteMetadataStore, directory: Path, tmp_path: Path
) -> None:
    create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)
    elsewhere = tmp_path / "models" / "churn-again"

    with pytest.raises(AlreadyExistsError, match="already a model named 'churn'"):
        create_model(metadata, elsewhere, "churn", "sklearn", Task.REGRESSION)

    assert not elsewhere.exists()


def test_a_directory_that_exists_is_left_alone(
    metadata: SqliteMetadataStore, directory: Path
) -> None:
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(AlreadyExistsError, match="already exists"):
        create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert [path.name for path in directory.iterdir()] == ["notes.txt"]
    assert metadata.get_model("churn") is None


def test_a_model_that_cannot_be_stored_leaves_nothing_behind(
    metadata: SqliteMetadataStore, directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("The disk is full")

    monkeypatch.setattr(metadata, "add_version", fail)

    with pytest.raises(RuntimeError, match="disk is full"):
        create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert not directory.exists()
    assert metadata.get_model("churn") is None


def test_an_interrupt_after_the_model_is_stored_keeps_its_directory(
    metadata: SqliteMetadataStore, directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transaction = metadata.transaction

    @contextmanager
    def interrupted() -> Generator[None]:
        with transaction():
            yield
        raise KeyboardInterrupt

    monkeypatch.setattr(metadata, "transaction", interrupted)

    with pytest.raises(KeyboardInterrupt):
        create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert metadata.get_model("churn") is not None
    assert (directory / "model.toml").is_file()


def test_a_file_in_the_place_of_the_models_directory_is_not_taken_for_the_model(
    metadata: SqliteMetadataStore, directory: Path
) -> None:
    directory.parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_model(metadata, directory, "churn", "sklearn", Task.BINARY_CLASSIFICATION)

    assert metadata.get_model("churn") is None


def test_a_flavor_without_a_template_leaves_nothing_behind(
    metadata: SqliteMetadataStore, directory: Path
) -> None:
    with pytest.raises(NotFoundError, match="no model template"):
        create_model(metadata, directory, "churn", "keras", Task.BINARY_CLASSIFICATION)

    assert not directory.exists()
    assert metadata.get_model("churn") is None


def test_a_name_that_is_not_valid_creates_nothing(
    metadata: SqliteMetadataStore, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="Invalid model name"):
        create_model(metadata, tmp_path / "models" / "Churn", "Churn", "sklearn", Task.REGRESSION)

    assert not (tmp_path / "models").exists()
