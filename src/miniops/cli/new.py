from pathlib import Path
from typing import Annotated

import typer

from miniops.adapters.stores import open_stores
from miniops.config.model import Flavor
from miniops.config.project import MODELS_DIR, find_project
from miniops.core.entities import Task, require_name
from miniops.core.registry import create_model


def _model_name(name: str) -> str:
    try:
        require_name("model", name)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    return name


def new(
    name: Annotated[str, typer.Argument(callback=_model_name, help="Name of the model.")],
    flavor: Annotated[Flavor, typer.Option(help="Framework the model is built with.")],
    task: Annotated[Task, typer.Option(help="What the model predicts.")],
) -> None:
    """Create a model: its directory and its first draft."""
    project = find_project(Path.cwd())
    directory = project.root / MODELS_DIR / name
    with open_stores(project) as stores:
        draft = create_model(stores.metadata, directory, name, flavor, task)
    typer.echo(f"Created the model {name!r} with the draft {draft.number} in {directory}")
