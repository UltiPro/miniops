from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from miniops.core.entities import Alias, Model, ModelVersion, Run
from miniops.core.versions import SemVer


class MetadataStore(Protocol):
    """The catalog of models, versions, runs and aliases.

    Only the miniOPs process on the host writes to it. Entities are immutable, so a change
    is always "build the new value, then store it here".
    """

    def add_model(self, model: Model) -> None:
        """Register a model.

        Raises:
            AlreadyExistsError: If the store has a model with this name.
        """

    def get_model(self, name: str) -> Model | None:
        """Return the model with this name, or None."""

    def list_models(self) -> Sequence[Model]:
        """Return all models, ordered by name."""

    def add_version(self, version: ModelVersion) -> None:
        """Add a draft to its model. A version is released later, with ``update_version``.

        Raises:
            InvalidStateError: If the version is not a draft.
            NotFoundError: If the store does not have its model.
            AlreadyExistsError: If the model has this number already, even as a deleted version.
        """

    def update_version(self, version: ModelVersion) -> None:
        """Replace the stored version that has the same id.

        Raises:
            NotFoundError: If the store has no version with this id, or the released run
                is not one of its runs.
            AlreadyExistsError: If another version of the model has the new number.
        """

    def delete_version(self, version_id: UUID) -> None:
        """Remove a draft with its runs, which frees its number.

        A released version is never removed: it is deleted by storing its tombstone.

        Raises:
            NotFoundError: If the store has no version with this id.
            InvalidStateError: If the version is not a draft.
        """

    def get_version(self, model_id: UUID, number: SemVer) -> ModelVersion | None:
        """Return the version of a model with this number, or None."""

    def list_versions(self, model_id: UUID) -> Sequence[ModelVersion]:
        """Return the versions of a model, highest number first."""

    def add_run(self, run: Run) -> None:
        """Add a run to its version.

        Raises:
            NotFoundError: If the store does not have its version or its parent run.
            AlreadyExistsError: If the store has a run with this id.
        """

    def update_run(self, run: Run) -> None:
        """Replace the stored run that has the same id.

        Raises:
            NotFoundError: If the store has no run with this id, or does not have its version
                or its parent run.
        """

    def get_run(self, run_id: UUID) -> Run | None:
        """Return the run with this id, or None."""

    def list_runs(self, version_id: UUID) -> Sequence[Run]:
        """Return the runs of a version, oldest first."""

    def set_alias(self, alias: Alias) -> None:
        """Create the alias, or move it when the model already has one with this name.

        Raises:
            NotFoundError: If the model has no version with this id.
        """

    def delete_alias(self, model_id: UUID, name: str) -> None:
        """Remove an alias of a model.

        Raises:
            NotFoundError: If the model has no alias with this name.
        """

    def get_alias(self, model_id: UUID, name: str) -> Alias | None:
        """Return the alias of a model with this name, or None."""

    def list_aliases(self, model_id: UUID) -> Sequence[Alias]:
        """Return the aliases of a model, ordered by name."""
