from typing import Annotated

import typer

from miniops.adapters.stores import open_stores
from miniops.cli.arguments import model_name
from miniops.cli.paths import current_directory
from miniops.config.model import Flavor
from miniops.config.project import MODELS_DIR, find_project
from miniops.core.entities import Task
from miniops.core.environments import sync_environment
from miniops.core.errors import ToolError, describe
from miniops.core.registry import create_model


def new(
    name: Annotated[str, typer.Argument(callback=model_name, help="Name of the model.")],
    flavor: Annotated[Flavor, typer.Option(help="Framework the model is built with.")],
    task: Annotated[Task, typer.Option(help="What the model predicts.")],
) -> None:
    """Create a model: its directory, its first draft and its environment."""
    project = find_project(current_directory())
    directory = project.root / MODELS_DIR / name
    with open_stores(project) as stores:
        draft = create_model(stores.metadata, directory, name, flavor, task)
    typer.echo(f"Created the model {name!r} with the draft {draft.number} in {directory}")
    try:
        sync_environment(directory)
    except ToolError as error:
        raise ToolError(_unfinished(name, str(error))) from error
    except OSError as error:
        raise OSError(_unfinished(name, describe(error))) from error


def _unfinished(name: str, reason: str) -> str:
    return (
        f"The model was created, but its environment was not: {reason}\n"
        f"Once that is fixed, run `miniops env sync {name}`."
    )
