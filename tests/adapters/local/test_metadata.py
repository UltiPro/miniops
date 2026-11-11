import math
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from miniops.adapters.local.metadata import SqliteMetadataStore
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

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
DIGEST = "a" * 64
ARTIFACT = ArtifactRef(key="models/churn/model.skops", digest=DIGEST, size=1024)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteMetadataStore]:
    with SqliteMetadataStore(tmp_path / "metadata.db") as opened:
        yield opened


def add_model(store: SqliteMetadataStore, name: str = "churn") -> Model:
    model = Model(
        id=uuid4(), name=name, flavor="sklearn", task="binary_classification", created_at=NOW
    )
    store.add_model(model)
    return model


def add_draft(store: SqliteMetadataStore, model: Model, number: str = "1.0.0") -> ModelVersion:
    version = ModelVersion(
        id=uuid4(), model_id=model.id, number=SemVer.parse(number), created_at=NOW
    )
    store.add_version(version)
    return version


def add_run(store: SqliteMetadataStore, version: ModelVersion, started_at: datetime = NOW) -> Run:
    run = Run(id=uuid4(), version_id=version.id, started_at=started_at, miniops_version="0.1.0a1")
    store.add_run(run)
    return run


def release(store: SqliteMetadataStore, version: ModelVersion) -> ModelVersion:
    run = add_run(store, version).finish(RunStatus.SUCCEEDED, LATER, artifact=ARTIFACT)
    store.update_run(run)
    released = version.release(run, DIGEST, LATER)
    store.update_version(released)
    return released


def test_a_model_comes_back_as_it_was_stored(store: SqliteMetadataStore) -> None:
    model = add_model(store)

    assert store.get_model("churn") == model


def test_an_unknown_model_is_none(store: SqliteMetadataStore) -> None:
    assert store.get_model("churn") is None


def test_models_are_listed_by_name(store: SqliteMetadataStore) -> None:
    for name in ("fraud", "churn", "demand"):
        add_model(store, name)

    assert [model.name for model in store.list_models()] == ["churn", "demand", "fraud"]


def test_a_model_name_is_used_once(store: SqliteMetadataStore) -> None:
    add_model(store)

    with pytest.raises(AlreadyExistsError, match="'churn' is already in the store"):
        add_model(store)


def test_a_draft_comes_back_as_it_was_stored(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = ModelVersion(
        id=uuid4(),
        model_id=model.id,
        number=SemVer(1, 1, 0),
        created_at=NOW,
        base=VersionRef(number=SemVer(1, 0, 0), digest=DIGEST),
    )

    store.add_version(version)

    assert store.get_version(model.id, SemVer(1, 1, 0)) == version
    assert store.get_version(model.id, SemVer(2, 0, 0)) is None


def test_a_version_needs_its_model(store: SqliteMetadataStore) -> None:
    stranger = Model(id=uuid4(), name="churn", flavor="sklearn", task="regression", created_at=NOW)
    version = ModelVersion(id=uuid4(), model_id=stranger.id, number=SemVer(1, 0, 0), created_at=NOW)

    with pytest.raises(NotFoundError, match="no model"):
        store.add_version(version)


def test_a_version_enters_the_store_as_a_draft(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    released = release(store, add_draft(store, model))

    with pytest.raises(InvalidStateError, match="enters the store as a draft"):
        store.add_version(replace(released, id=uuid4(), number=SemVer(2, 0, 0)))


def test_versions_are_listed_highest_first(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    for number in ("1.2.0", "1.10.0", "2.0.0", "1.2.1"):
        add_draft(store, model, number)

    numbers = [str(version.number) for version in store.list_versions(model.id)]

    assert numbers == ["2.0.0", "1.10.0", "1.2.1", "1.2.0"]


def test_a_number_is_used_once_per_model(store: SqliteMetadataStore) -> None:
    churn, fraud = add_model(store, "churn"), add_model(store, "fraud")
    add_draft(store, churn, "1.0.0")

    add_draft(store, fraud, "1.0.0")
    with pytest.raises(AlreadyExistsError, match=r"already has a version 1\.0\.0"):
        add_draft(store, churn, "1.0.0")


def test_a_renumbered_draft_is_found_under_its_new_number(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = add_draft(store, model, "1.1.0").renumber(SemVer(2, 0, 0))

    store.update_version(version)

    assert store.get_version(model.id, SemVer(2, 0, 0)) == version
    assert store.get_version(model.id, SemVer(1, 1, 0)) is None


def test_a_draft_cannot_take_the_number_of_another_version(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    add_draft(store, model, "1.0.0")
    version = add_draft(store, model, "1.1.0")

    with pytest.raises(AlreadyExistsError, match=r"already has a version 1\.0\.0"):
        store.update_version(version.renumber(SemVer(1, 0, 0)))


def test_only_a_stored_version_can_be_updated(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = ModelVersion(id=uuid4(), model_id=model.id, number=SemVer(1, 0, 0), created_at=NOW)

    with pytest.raises(NotFoundError, match="no version"):
        store.update_version(version)


def test_a_released_version_comes_back_with_its_run_digest_and_date(
    store: SqliteMetadataStore,
) -> None:
    model = add_model(store)
    released = release(store, add_draft(store, model))

    stored = store.get_version(model.id, SemVer(1, 0, 0))

    assert stored == released
    assert stored.status is VersionStatus.RELEASED


def test_a_version_is_released_only_with_its_own_run(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version, other = add_draft(store, model, "1.0.0"), add_draft(store, model, "2.0.0")
    run = add_run(store, other).finish(RunStatus.SUCCEEDED, LATER, artifact=ARTIFACT)
    store.update_run(run)
    forged = replace(
        version,
        status=VersionStatus.RELEASED,
        released_run_id=run.id,
        content_digest=DIGEST,
        released_at=LATER,
    )

    with pytest.raises(NotFoundError, match=r"is not a run of version 1\.0\.0"):
        store.update_version(forged)


def test_a_deleted_version_keeps_its_number(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    tombstone = release(store, add_draft(store, model)).delete()

    store.update_version(tombstone)

    assert store.get_version(model.id, SemVer(1, 0, 0)) == tombstone
    with pytest.raises(AlreadyExistsError, match=r"already has a version 1\.0\.0"):
        add_draft(store, model, "1.0.0")


def test_removing_a_draft_takes_its_runs_and_frees_its_number(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = add_draft(store, model)
    tuning = add_run(store, version)
    trial = replace(add_run(store, version), parent_run_id=tuning.id)
    store.update_run(trial)

    store.delete_version(version.id)

    assert store.list_versions(model.id) == []
    assert store.get_run(tuning.id) is None
    assert store.get_run(trial.id) is None
    add_draft(store, model, "1.0.0")


def test_only_a_draft_can_be_removed(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    released = release(store, add_draft(store, model))

    with pytest.raises(InvalidStateError, match=r"1\.0\.0 is released, only a draft"):
        store.delete_version(released.id)
    with pytest.raises(NotFoundError, match="no version"):
        store.delete_version(uuid4())


def test_a_run_comes_back_as_it_was_stored(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    tuning = add_run(store, version)
    run = Run(
        id=uuid4(),
        version_id=version.id,
        started_at=NOW,
        miniops_version="0.1.0a1",
        status=RunStatus.SUCCEEDED,
        parent_run_id=tuning.id,
        params={"max_depth": 6, "class_weight": {"0": 1.0, "1": 2.5}, "features": ["age", "plan"]},
        metrics={"roc_auc": 0.87, "log_loss": 0.31},
        dataset=DatasetRef(uri="data/train.parquet", fingerprint=DIGEST),
        snapshot=ArtifactRef(key="snapshots/ab/cdef.zip", digest="b" * 64, size=2048),
        lock_digest="c" * 64,
        code_commit="5d73e7c",
        artifact=ARTIFACT,
        signature=Signature(
            inputs=(Column("age", "Int64"), Column("plan", "String", nullable=True)),
            outputs=(Column("churn", "Float64"),),
        ),
        finished_at=LATER,
    )

    store.add_run(run)

    assert store.get_run(run.id) == run


def test_a_failed_run_keeps_its_error(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    run = add_run(store, version).finish(RunStatus.FAILED, LATER, error="out of memory")

    store.update_run(run)

    assert store.get_run(run.id) == run


def test_an_unknown_run_is_none(store: SqliteMetadataStore) -> None:
    assert store.get_run(uuid4()) is None


def test_a_run_needs_its_version_and_its_parent(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    orphan = Run(id=uuid4(), version_id=uuid4(), started_at=NOW, miniops_version="0.1.0a1")
    trial = replace(orphan, version_id=version.id, parent_run_id=uuid4())

    with pytest.raises(NotFoundError, match="not in the store"):
        store.add_run(orphan)
    with pytest.raises(NotFoundError, match="not in the store"):
        store.add_run(trial)


def test_a_run_id_is_used_once(store: SqliteMetadataStore) -> None:
    run = add_run(store, add_draft(store, add_model(store)))

    with pytest.raises(AlreadyExistsError, match="already in the store"):
        store.add_run(run)


def test_only_a_stored_run_can_be_updated(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    run = Run(id=uuid4(), version_id=version.id, started_at=NOW, miniops_version="0.1.0a1")

    with pytest.raises(NotFoundError, match="no run"):
        store.update_run(run)


def test_runs_are_listed_oldest_first(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    third = add_run(store, version, NOW + timedelta(seconds=2))
    first = add_run(store, version, NOW)
    second = add_run(store, version, NOW + timedelta(seconds=1, microseconds=5))

    assert store.list_runs(version.id) == [first, second, third]


def test_a_metric_that_is_not_a_number_survives(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    run = add_run(store, version).finish(
        RunStatus.FAILED, LATER, metrics={"loss": math.nan}, error="the loss diverged"
    )

    store.update_run(run)

    stored = store.get_run(run.id)
    assert stored is not None
    assert math.isnan(stored.metrics["loss"])


def test_a_moment_comes_back_in_utc(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    warsaw = datetime(2026, 11, 11, 13, 0, tzinfo=timezone(timedelta(hours=1)))

    run = add_run(store, version, warsaw)

    stored = store.get_run(run.id)
    assert stored is not None
    assert stored.started_at == warsaw
    assert stored.started_at.utcoffset() == timedelta(0)


def test_a_status_the_schema_does_not_know_is_refused(store: SqliteMetadataStore) -> None:
    version = add_draft(store, add_model(store))
    run = Run(
        id=uuid4(),
        version_id=version.id,
        started_at=NOW,
        miniops_version="0.1.0a1",
        status=cast(RunStatus, "paused"),
        finished_at=LATER,
    )

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        store.add_run(run)


def test_an_alias_is_created_and_then_moved(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    first = release(store, add_draft(store, model, "1.0.0"))
    second = release(store, add_draft(store, model, "1.1.0"))
    alias = Alias(model_id=model.id, name="champion", version_id=first.id, updated_at=NOW)

    store.set_alias(alias)
    assert store.get_alias(model.id, "champion") == alias

    moved = replace(alias, version_id=second.id, updated_at=LATER)
    store.set_alias(moved)
    assert store.list_aliases(model.id) == [moved]


def test_aliases_are_listed_by_name(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = release(store, add_draft(store, model))
    for name in ("champion", "baseline", "challenger"):
        store.set_alias(Alias(model_id=model.id, name=name, version_id=version.id, updated_at=NOW))

    names = [alias.name for alias in store.list_aliases(model.id)]

    assert names == ["baseline", "challenger", "champion"]


def test_an_alias_points_at_a_version_of_its_own_model(store: SqliteMetadataStore) -> None:
    churn, fraud = add_model(store, "churn"), add_model(store, "fraud")
    version = release(store, add_draft(store, fraud))
    alias = Alias(model_id=churn.id, name="champion", version_id=version.id, updated_at=NOW)

    with pytest.raises(NotFoundError, match="no version"):
        store.set_alias(alias)
    with pytest.raises(NotFoundError, match="no version"):
        store.set_alias(replace(alias, version_id=uuid4()))


def test_an_alias_can_be_removed(store: SqliteMetadataStore) -> None:
    model = add_model(store)
    version = release(store, add_draft(store, model))
    store.set_alias(
        Alias(model_id=model.id, name="champion", version_id=version.id, updated_at=NOW)
    )

    store.delete_alias(model.id, "champion")

    assert store.get_alias(model.id, "champion") is None
    with pytest.raises(NotFoundError, match="no alias 'champion'"):
        store.delete_alias(model.id, "champion")


def test_a_store_keeps_its_content_between_sessions(tmp_path: Path) -> None:
    path = tmp_path / "project" / ".miniops" / "metadata.db"
    with SqliteMetadataStore(path) as store:
        model = add_model(store)
        version = add_draft(store, model)
        run = add_run(store, version)

    with SqliteMetadataStore(path) as store:
        assert store.list_models() == [model]
        assert store.list_versions(model.id) == [version]
        assert store.list_runs(version.id) == [run]
