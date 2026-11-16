import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from miniops.core.entities import Alias, Model, ModelVersion, Task
from miniops.core.errors import AlreadyExistsError, NotFoundError
from miniops.core.versions import FIRST_VERSION
from miniops.ports.metadata import MetadataStore
from miniops.templates import write_model_files


@dataclass(frozen=True)
class CatalogEntry:
    """A model with its versions, highest number first, and its aliases."""

    model: Model
    versions: Sequence[ModelVersion]
    aliases: Sequence[Alias]

    def aliases_of(self, version: ModelVersion) -> list[str]:
        """Return the names of the aliases that point at a version."""
        return [alias.name for alias in self.aliases if alias.version_id == version.id]

    def find_version(self, ref: str) -> ModelVersion:
        """Return the version with this number, or the one that this alias points at.

        Raises:
            NotFoundError: If the model has neither.
        """
        named = {alias.version_id for alias in self.aliases if alias.name == ref}
        for version in self.versions:
            if str(version.number) == ref or version.id in named:
                return version
        raise NotFoundError(f"The model {self.model.name!r} has no version or alias {ref!r}.")


def list_catalog(metadata: MetadataStore) -> list[CatalogEntry]:
    """Return every model, ordered by name."""
    return [_entry(metadata, model) for model in metadata.list_models()]


def find_model(metadata: MetadataStore, name: str) -> CatalogEntry:
    """Return the model with this name.

    Raises:
        NotFoundError: If there is no such model.
    """
    model = metadata.get_model(name)
    if model is None:
        raise NotFoundError(f"There is no model named {name!r}.")
    return _entry(metadata, model)


def create_model(
    metadata: MetadataStore, directory: Path, name: str, flavor: str, task: Task
) -> ModelVersion:
    """Create a model: its directory from the template of the flavor, and its first draft.

    Returns the draft. The directory is removed again when the model cannot be stored.

    Raises:
        AlreadyExistsError: If there is a model with this name already, or the directory exists.
        NotFoundError: If miniOPs has no template for the flavor.
    """
    now = datetime.now(UTC)
    model = Model(id=uuid4(), name=name, flavor=flavor, task=task, created_at=now)
    draft = ModelVersion(id=uuid4(), model_id=model.id, number=FIRST_VERSION, created_at=now)
    if metadata.get_model(name) is not None:
        raise AlreadyExistsError(f"There is already a model named {name!r}.")
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as error:
        raise AlreadyExistsError(f"{directory} already exists.") from error
    try:
        write_model_files(directory, name, flavor, task)
        with metadata.transaction():
            metadata.add_model(model)
            metadata.add_version(draft)
    except BaseException:
        # An interrupt can arrive after the commit, and a stored model keeps its directory.
        stored = metadata.get_model(name)
        if stored is None or stored.id != model.id:
            shutil.rmtree(directory, ignore_errors=True)
        raise
    return draft


def _entry(metadata: MetadataStore, model: Model) -> CatalogEntry:
    return CatalogEntry(
        model=model,
        versions=metadata.list_versions(model.id),
        aliases=metadata.list_aliases(model.id),
    )
