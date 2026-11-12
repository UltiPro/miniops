from pathlib import Path
from typing import Annotated

import typer

from miniops.config.project import init_project


def init(
    name: Annotated[
        str | None,
        typer.Option(help="Name of the project. The default is the name of the directory."),
    ] = None,
) -> None:
    """Create a miniOPs project in the current directory."""
    project = init_project(Path.cwd(), name)
    typer.echo(f"Created the project {project.config.project.name!r} in {project.root}")
