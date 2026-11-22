from typing import Annotated

import typer

from miniops.cli.arguments import model_name
from miniops.cli.paths import current_directory
from miniops.config.project import MODELS_DIR, find_project
from miniops.core.environments import sync_environment

env_app = typer.Typer(help="Manage the environments of models.", no_args_is_help=True)


@env_app.command("sync")
def sync(
    model: Annotated[str, typer.Argument(callback=model_name, help="Name of the model.")],
) -> None:
    """Create or update the environment of a model from its pyproject.toml and uv.lock."""
    project = find_project(current_directory())
    sync_environment(project.root / MODELS_DIR / model)
