import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from miniops.core.errors import InvalidStateError
from miniops.core.versions import SemVer

type Json = str | int | float | bool | list[Json] | dict[str, Json] | None

# Fits a Cloud Run service name, so one name works as a directory, an image and a service.
_NAME = re.compile(r"[a-z]([a-z0-9-]{0,47}[a-z0-9])?")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEY = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")


def _require_name(kind: str, name: str) -> None:
    if _NAME.fullmatch(name) is None:
        raise ValueError(
            f"Invalid {kind} name: {name!r}. Use lowercase letters, digits and '-', "
            "starting with a letter, at most 49 characters."
        )


def _require_digest(digest: str) -> None:
    if _SHA256.fullmatch(digest) is None:
        raise ValueError(f"Not a SHA-256 digest: {digest!r}")


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("Timestamps need a time zone, for example datetime.now(UTC).")


class VersionStatus(StrEnum):
    """Where a version is in its life."""

    DRAFT = "draft"
    RELEASED = "released"
    DELETED = "deleted"


class RunStatus(StrEnum):
    """How a run is doing or how it ended."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class ArtifactRef:
    """A file in the artifact store: where it is and what it contains."""

    key: str
    digest: str
    size: int

    def __post_init__(self) -> None:
        # Keys are relative and use "/", so a store can move to another disk, system or bucket.
        if _KEY.fullmatch(self.key) is None or {".", ".."} & set(self.key.split("/")):
            raise ValueError(f"Not a valid artifact key: {self.key!r}")
        _require_digest(self.digest)
        if self.size < 0:
            raise ValueError(f"Artifact size cannot be negative: {self.size}")


@dataclass(frozen=True)
class DatasetRef:
    """Where the training data came from and a fingerprint of its content.

    miniOPs never stores the data itself.
    """

    uri: str
    fingerprint: str

    def __post_init__(self) -> None:
        _require_digest(self.fingerprint)


@dataclass(frozen=True)
class Column:
    """One column of a model's input or output."""

    name: str
    dtype: str
    nullable: bool = False


@dataclass(frozen=True)
class Signature:
    """The columns a model expects and the columns it returns."""

    inputs: tuple[Column, ...]
    outputs: tuple[Column, ...]


@dataclass(frozen=True)
class VersionRef:
    """Points at a released version by number and content.

    It keeps its meaning in a store that does not have that version, for example after a migration.
    """

    number: SemVer
    digest: str

    def __post_init__(self) -> None:
        _require_digest(self.digest)


@dataclass(frozen=True, kw_only=True)
class Model:
    """A model in the catalog."""

    id: UUID
    name: str
    flavor: str
    task: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_name("model", self.name)
        _require_aware(self.created_at)


@dataclass(frozen=True, kw_only=True)
class Run:
    """One training attempt inside a draft version."""

    id: UUID
    version_id: UUID
    started_at: datetime
    miniops_version: str
    status: RunStatus = RunStatus.RUNNING
    parent_run_id: UUID | None = None
    params: Mapping[str, Json] = field(default_factory=dict)
    metrics: Mapping[str, float] = field(default_factory=dict)
    dataset: DatasetRef | None = None
    snapshot: ArtifactRef | None = None
    lock_digest: str | None = None
    code_commit: str | None = None
    artifact: ArtifactRef | None = None
    signature: Signature | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.started_at)
        if self.lock_digest is not None:
            _require_digest(self.lock_digest)
        if self.status is RunStatus.RUNNING:
            if self.finished_at is not None:
                raise ValueError("A running run cannot have an end time.")
        elif self.finished_at is None:
            raise ValueError("A finished run needs an end time.")
        else:
            _require_aware(self.finished_at)

    def finish(
        self,
        status: RunStatus,
        at: datetime,
        *,
        metrics: Mapping[str, float] | None = None,
        artifact: ArtifactRef | None = None,
        signature: Signature | None = None,
        error: str | None = None,
    ) -> Self:
        """Record how the run ended.

        Raises:
            InvalidStateError: If the run has already ended.
        """
        if self.status is not RunStatus.RUNNING:
            raise InvalidStateError(f"Run {self.id} has already ended as {self.status}.")
        if status is RunStatus.RUNNING:
            raise ValueError("A run cannot end as running.")
        return replace(
            self,
            status=status,
            finished_at=at,
            metrics=self.metrics if metrics is None else metrics,
            artifact=artifact,
            signature=signature,
            error=error,
        )


@dataclass(frozen=True, kw_only=True)
class ModelVersion:
    """One version of a model: first a draft that collects runs, then released and immutable."""

    id: UUID
    model_id: UUID
    number: SemVer
    created_at: datetime
    status: VersionStatus = VersionStatus.DRAFT
    base: VersionRef | None = None
    released_run_id: UUID | None = None
    content_digest: str | None = None
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at)
        if self.status is VersionStatus.DRAFT:
            if (self.released_run_id, self.content_digest, self.released_at) != (None, None, None):
                raise ValueError("A draft cannot have a released run, a digest or a release date.")
            return
        if self.released_run_id is None or self.content_digest is None or self.released_at is None:
            raise ValueError("A released version needs its run, its digest and its release date.")
        _require_digest(self.content_digest)
        _require_aware(self.released_at)

    def renumber(self, number: SemVer) -> Self:
        """Give a draft another number, for example after a refused release.

        Raises:
            InvalidStateError: If the version is not a draft.
        """
        self._require_draft("renumbered")
        return replace(self, number=number)

    def release(self, run: Run, content_digest: str, at: datetime) -> Self:
        """Freeze the draft with one of its runs.

        Raises:
            InvalidStateError: If the version is not a draft, or the run is not a successful
                run of this version with a model artifact.
        """
        self._require_draft("released")
        if run.version_id != self.id:
            raise InvalidStateError(f"Run {run.id} does not belong to version {self.number}.")
        if run.status is not RunStatus.SUCCEEDED or run.artifact is None:
            raise InvalidStateError(
                f"Run {run.id} cannot be released: it must be successful and have a model artifact."
            )
        return replace(
            self,
            status=VersionStatus.RELEASED,
            released_run_id=run.id,
            content_digest=content_digest,
            released_at=at,
        )

    def delete(self) -> Self:
        """Turn a released version into a tombstone, so its number is never used again.

        Raises:
            InvalidStateError: If the version is not released. A draft is simply removed.
        """
        if self.status is not VersionStatus.RELEASED:
            raise InvalidStateError(
                f"Version {self.number} is {self.status}, only a released one leaves a tombstone."
            )
        return replace(self, status=VersionStatus.DELETED)

    def _require_draft(self, action: str) -> None:
        if self.status is not VersionStatus.DRAFT:
            raise InvalidStateError(
                f"Version {self.number} is {self.status}, only a draft can be {action}."
            )


@dataclass(frozen=True, kw_only=True)
class Alias:
    """A movable name, such as ``champion``, for a released version of a model."""

    model_id: UUID
    name: str
    version_id: UUID
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_name("alias", self.name)
        _require_aware(self.updated_at)
