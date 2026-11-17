import logging
import shlex
import sys
from typing import NoReturn

import typer

from miniops import __version__
from miniops.cli.app import app
from miniops.cli.log import CommandLog, project_log
from miniops.core.errors import MiniopsError

__all__ = ["app", "main"]

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the command line.

    An error ends with a short message. The log of the project keeps its traceback, unless
    miniOPs reported the error itself.
    """
    with project_log() as command_log:
        logger.info("miniops %s: %s", __version__, shlex.join(sys.argv[1:]))
        try:
            app(prog_name="miniops")
        except MiniopsError as error:
            logger.error("Command failed: %s", error)
            _fail(f"Error: {error}")
        except OSError as error:
            # A full disk or a missing permission is a problem of the system, not a bug.
            message = _describe(error)
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


def _describe(error: OSError) -> str:
    # str() adds the number of the error and shows a path as Python code, with every
    # backslash doubled on Windows.
    if error.strerror is None:
        return str(error)
    files = (error.filename, error.filename2)
    names = " -> ".join(str(name) for name in files if name is not None)
    return f"{error.strerror}: {names}" if names else error.strerror


def _fail(message: str, command_log: CommandLog | None = None) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    if command_log is not None and command_log.saved:
        typer.echo(f"Details: {command_log.file}", err=True)
    raise SystemExit(1)
