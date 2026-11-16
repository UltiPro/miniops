from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from miniops.adapters.local.metadata import SqliteMetadataStore
from miniops.config.model import load_model_config
from miniops.core.entities import (
    Alias,
    ArtifactRef,
    ModelVersion,
    Run,
    RunStatus,
    Task,
    VersionStatus,
)
from miniops.core.errors import AlreadyExistsError, NotFoundError
from miniops.core.registry import create_model, find_model, list_catalog
from miniops.core.versions import FIRST_VERSION, SemVer

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def metadata(tmp_path: Path) -> Iterator[SqliteMetadataStore]:
    with SqliteMetadataStore(tmp_path / ".miniops" / "metadata.db") as store:
        yield store


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    return tmp_path / "models" / "churn"


def release(metadata: SqliteMetadataStore, version: ModelVersion) -> ModelVersion:
    run = Run(id=uuid4(), version_id=version.id, started_at=NOW, miniops_version="0.1.0")
    metadata.add_run(run)
    artifact = ArtifactRef(key="runs/7c1e/model.skops", digest="a" * 64, size=1)
    run = run.finish(RunStatus.SUCCEEDED, NOW, artifact=artifact)
    metadata.update_run(run)
    released = version.release(run, "b" * 64, NOW)
    metadata.update_version(released)
    return released


def next_draft(metadata: SqliteMetadataStore, first: ModelVersion) -> ModelVersion:
    draft = ModelVersion(
        id=uuid4(), model_id=first.model_id, number=SemVer(1, 1, 0), created_at=NOW
    )
    metadata.add_version(draft)
    return draft


def champion(metadata: SqliteMetadataStore, version: ModelVersion) -> Alias:
    alias = Alias(model_id=version.model_id, name="champion", version_id=version.id, updated_at=NOW)
    metadata.set_alias(alias)
    return alias


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


def test_the_catalog_has_every_model_with_its_versions_and_aliases(
    metadata: SqliteMetadataStore, directory: Path, tmp_path: Path
) -> None:
    demand = create_model(
        metadata, tmp_path / "models" / "demand", "demand", "sklearn", Task.REGRESSION
    )
    released = release(
        metadata, create_model(metadata, directory, "churn", "sklearn", Task.REGRESSION)
    )
    alias = champion(metadata, released)
    draft = next_draft(metadata, released)

    churn_entry, demand_entry = list_catalog(metadata)

    assert churn_entry.model.name == "churn"
    assert churn_entry.versions == [draft, released]
    assert churn_entry.aliases == [alias]
    assert demand_entry.model.name == "demand"
    assert demand_entry.versions == [demand]
    assert demand_entry.aliases == []


def test_a_model_is_found_by_its_name(metadata: SqliteMetadataStore, directory: Path) -> None:
    draft = create_model(metadata, directory, "churn", "sklearn", Task.REGRESSION)

    entry = find_model(metadata, "churn")

    assert entry.model.name == "churn"
    assert entry.versions == [draft]


def test_a_model_that_is_not_there_is_not_found(metadata: SqliteMetadataStore) -> None:
    with pytest.raises(NotFoundError, match="no model named 'fraud'"):
        find_model(metadata, "fraud")


def test_a_version_is_found_by_its_number_or_by_an_alias(
    metadata: SqliteMetadataStore, directory: Path
) -> None:
    released = release(
        metadata, create_model(metadata, directory, "churn", "sklearn", Task.REGRESSION)
    )
    champion(metadata, released)
    draft = next_draft(metadata, released)

    entry = find_model(metadata, "churn")

    assert entry.find_version("1.1.0") == draft
    assert entry.find_version("1.0.0") == released
    assert entry.find_version("champion") == released
    assert entry.aliases_of(released) == ["champion"]
    assert entry.aliases_of(draft) == []


@pytest.mark.parametrize("ref", ["2.0.0", "challenger", "1.0", ""])
def test_a_version_that_is_not_there_is_not_found(
    metadata: SqliteMetadataStore, directory: Path, ref: str
) -> None:
    create_model(metadata, directory, "churn", "sklearn", Task.REGRESSION)

    with pytest.raises(NotFoundError, match="has no version or alias"):
        find_model(metadata, "churn").find_version(ref)
