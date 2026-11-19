import io
import logging
import shlex
import sys
from typing import NoReturn

import typer

from miniops import __version__
from miniops.cli.app import app
from miniops.cli.log import CommandLog, project_log
from miniops.cli.output import describe
from miniops.core.errors import MiniopsError

__all__ = ["app", "main"]

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the command line.

    An error ends with a short message. The log of the project keeps its traceback, unless
    miniOPs reported the error itself.
    """
    # Redirected on Windows, the output is in the ANSI code page, which has no place for every
    # character of a name or a path.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")
    with project_log() as command_log:
        logger.info("miniops %s: %s", __version__, shlex.join(sys.argv[1:]))
        try:
            app(prog_name="miniops")
        except MiniopsError as error:
            logger.error("Command failed: %s", error)
            _fail(f"Error: {error}")
        except OSError as error:
            # A full disk or a missing permission is a problem of the system, not a bug.
            message = describe(error)
            logger.error("Command failed: %s", message, exc_info=True)
            _fail(f"Error: {message}", command_log)
        except Exception as error:
            logger.critical("Unexpected error", exc_info=True)
            if command_log is None or not command_log.saved:
                raise
            _fail(
                f"Error: miniOPs hit an unexpected error ({type(error).__name__}: {error}). "
                "This is a bug.",
                command_log,
            )


def _fail(message: str, command_log: CommandLog | None = None) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    if command_log is not None and command_log.saved:
        typer.echo(f"Details: {command_log.file}", err=True)
    raise SystemExit(1)
