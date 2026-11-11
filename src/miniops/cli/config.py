from pathlib import Path

import typer

from miniops.config.project import find_project

config_app = typer.Typer(help="Look at the configuration.", no_args_is_help=True)


@config_app.command("show")
def show() -> None:
    """Show the configuration of the project in the current directory."""
    project = find_project(Path.cwd())
    typer.echo(f"Project root    {project.root}")
    typer.echo(f"Name            {project.config.project.name}")
    typer.echo(f"Default target  {project.config.project.default_target}")
