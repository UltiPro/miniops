import platform
from typing import Annotated

import typer

from miniops import __version__

app = typer.Typer(
    name="miniops",
    help="Lightweight, polars-native MLOps CLI.",
    no_args_is_help=True,
)


def _print_version(value: bool) -> None:
    """Print the short version string and stop, when ``--version`` is given."""
    if value:
        typer.echo(f"miniops {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the miniOPs version and exit.",
        ),
    ] = False,
) -> None:
    """Lightweight, polars-native MLOps CLI."""


@app.command("version")
def version_command() -> None:
    """Show detailed version information, useful for bug reports."""
    typer.echo(f"miniOPs       {__version__}")
    typer.echo(f"Python        {platform.python_version()} ({platform.python_implementation()})")
    typer.echo(f"OS            {platform.platform()}")
    typer.echo(f"Architecture  {platform.machine()}")
