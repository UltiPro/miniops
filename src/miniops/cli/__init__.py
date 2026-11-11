import typer

from miniops.cli.app import app
from miniops.core.errors import MiniopsError

__all__ = ["app", "main"]


def main() -> None:
    """Run the command line. An error that miniOPs reports ends with a message, not a traceback."""
    try:
        app(prog_name="miniops")
    except MiniopsError as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from None
