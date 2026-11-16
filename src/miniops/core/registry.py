import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from miniops.core.entities import Model, ModelVersion, Task
from miniops.core.errors import AlreadyExistsError
from miniops.core.versions import FIRST_VERSION
from miniops.ports.metadata import MetadataStore
from miniops.templates import write_model_files


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
