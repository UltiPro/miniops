from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from miniops.core.entities import (
    Alias,
    ArtifactRef,
    DatasetRef,
    Model,
    ModelVersion,
    Run,
    RunStatus,
    VersionRef,
    VersionStatus,
)
from miniops.core.errors import InvalidStateError
from miniops.core.versions import FIRST_VERSION, SemVer

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 11, 12, 5, tzinfo=UTC)
DIGEST = "a" * 64
ARTIFACT = ArtifactRef(key="models/churn/model.skops", digest=DIGEST, size=1024)


def draft() -> ModelVersion:
    return ModelVersion(id=uuid4(), model_id=uuid4(), number=FIRST_VERSION, created_at=NOW)


def running_run(version: ModelVersion) -> Run:
    return Run(id=uuid4(), version_id=version.id, started_at=NOW, miniops_version="0.1.0a1")


def successful_run(version: ModelVersion) -> Run:
    return running_run(version).finish(
        RunStatus.SUCCEEDED, LATER, metrics={"roc_auc": 0.87}, artifact=ARTIFACT
    )


def released() -> ModelVersion:
    version = draft()
    return version.release(successful_run(version), DIGEST, LATER)


@pytest.mark.parametrize("name", ["churn", "churn-v2", "a", "x" * 49])
def test_model_accepts_names_that_work_everywhere(name: str) -> None:
    model = Model(
        id=uuid4(), name=name, flavor="sklearn", task="binary_classification", created_at=NOW
    )

    assert model.name == name


@pytest.mark.parametrize(
    "name", ["", "Churn", "2churn", "churn_v2", "churn-", "my model", "x" * 50]
)
def test_model_rejects_other_names(name: str) -> None:
    with pytest.raises(ValueError, match="Invalid model name"):
        Model(id=uuid4(), name=name, flavor="sklearn", task="binary_classification", created_at=NOW)


def test_timestamps_need_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        ModelVersion(
            id=uuid4(), model_id=uuid4(), number=FIRST_VERSION, created_at=datetime(2026, 11, 11)
        )


@pytest.mark.parametrize(
    "key", ["", "/abs/model.skops", "a/../b", "./a", "a//b", "a\\b", "C:/a", "a/"]
)
def test_artifact_keys_are_relative_and_portable(key: str) -> None:
    with pytest.raises(ValueError, match="artifact key"):
        ArtifactRef(key=key, digest=DIGEST, size=1)


@pytest.mark.parametrize("digest", ["", "abc", "A" * 64, "g" * 64])
def test_digests_are_sha256_in_lowercase_hex(digest: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ArtifactRef(key="a/b", digest=digest, size=1)
    with pytest.raises(ValueError, match="SHA-256"):
        DatasetRef(uri="data/train.parquet", fingerprint=digest)
    with pytest.raises(ValueError, match="SHA-256"):
        VersionRef(number=FIRST_VERSION, digest=digest)


def test_artifact_size_cannot_be_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        ArtifactRef(key="a/b", digest=DIGEST, size=-1)


def test_a_draft_can_be_renumbered() -> None:
    version = draft().renumber(SemVer(2, 0, 0))

    assert version.number == SemVer(2, 0, 0)
    assert version.status is VersionStatus.DRAFT


def test_a_draft_has_nothing_released() -> None:
    with pytest.raises(ValueError, match="draft"):
        replace(draft(), content_digest=DIGEST)


def test_release_freezes_the_draft_with_its_run() -> None:
    version = draft()
    run = successful_run(version)

    result = version.release(run, DIGEST, LATER)

    assert result.status is VersionStatus.RELEASED
    assert result.released_run_id == run.id
    assert result.content_digest == DIGEST
    assert result.released_at == LATER


def test_release_refuses_a_run_of_another_version() -> None:
    with pytest.raises(InvalidStateError, match="does not belong"):
        draft().release(successful_run(draft()), DIGEST, LATER)


def test_release_refuses_a_run_that_is_not_successful() -> None:
    version = draft()
    failed = running_run(version).finish(RunStatus.FAILED, LATER, error="out of memory")

    with pytest.raises(InvalidStateError, match="cannot be released"):
        version.release(failed, DIGEST, LATER)


def test_release_refuses_a_run_without_a_model_artifact() -> None:
    version = draft()
    trial = running_run(version).finish(RunStatus.SUCCEEDED, LATER, metrics={"roc_auc": 0.8})

    with pytest.raises(InvalidStateError, match="cannot be released"):
        version.release(trial, DIGEST, LATER)


def test_a_released_version_cannot_change() -> None:
    version = released()

    with pytest.raises(InvalidStateError, match="only a draft"):
        version.renumber(SemVer(1, 0, 1))
    with pytest.raises(InvalidStateError, match="only a draft"):
        version.release(successful_run(version), DIGEST, LATER)


def test_a_released_version_needs_its_run_digest_and_date() -> None:
    with pytest.raises(ValueError, match="released version needs"):
        replace(released(), released_at=None)


def test_deleting_a_released_version_leaves_a_tombstone() -> None:
    version = released().delete()

    assert version.status is VersionStatus.DELETED
    assert version.content_digest == DIGEST


def test_a_draft_leaves_no_tombstone() -> None:
    with pytest.raises(InvalidStateError, match="tombstone"):
        draft().delete()


def test_a_run_starts_as_running_and_records_how_it_ended() -> None:
    run = successful_run(draft())

    assert run.status is RunStatus.SUCCEEDED
    assert run.finished_at == LATER
    assert run.metrics == {"roc_auc": 0.87}
    assert run.artifact == ARTIFACT


def test_a_run_ends_only_once() -> None:
    with pytest.raises(InvalidStateError, match="already ended"):
        successful_run(draft()).finish(RunStatus.FAILED, LATER)


def test_a_run_cannot_end_as_running() -> None:
    with pytest.raises(ValueError, match="cannot end as running"):
        running_run(draft()).finish(RunStatus.RUNNING, LATER)


def test_run_state_and_end_time_have_to_agree() -> None:
    run = running_run(draft())

    with pytest.raises(ValueError, match="running run"):
        replace(run, finished_at=LATER)
    with pytest.raises(ValueError, match="needs an end time"):
        replace(run, status=RunStatus.FAILED)
    with pytest.raises(ValueError, match="time zone"):
        replace(run, status=RunStatus.FAILED, finished_at=datetime(2026, 11, 11))


def test_a_run_checks_its_lock_digest() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        replace(running_run(draft()), lock_digest="not-a-digest")
    assert replace(running_run(draft()), lock_digest=DIGEST).lock_digest == DIGEST


def test_alias_names_follow_the_same_rule_as_model_names() -> None:
    alias = Alias(model_id=uuid4(), name="champion", version_id=uuid4(), updated_at=NOW)

    assert alias.name == "champion"
    with pytest.raises(ValueError, match="Invalid alias name"):
        replace(alias, name="Champion")
