import logging
import shlex
import sys

import typer

from miniops import __version__
from miniops.cli.app import app
from miniops.cli.log import project_log
from miniops.core.errors import MiniopsError

__all__ = ["app", "main"]

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the command line.

    An error ends with a short message, and its traceback goes to the log of the project.
    """
    with project_log() as command_log:
        logger.info("miniops %s: %s", __version__, shlex.join(sys.argv[1:]))
        try:
            app(prog_name="miniops")
        except MiniopsError as error:
            logger.error("Command failed: %s", error, exc_info=True)
            typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
            raise SystemExit(1) from None
        except Exception as error:
            logger.critical("Unexpected error", exc_info=True)
            if command_log is None or not command_log.saved:
                raise
            typer.secho(
                f"Error: miniOPs hit an unexpected error ({type(error).__name__}: {error}). "
                "This is a bug.",
                fg=typer.colors.RED,
                err=True,
            )
            typer.echo(f"Details: {command_log.file}", err=True)
            raise SystemExit(1) from None
