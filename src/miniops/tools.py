import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryFile
from typing import IO

_TIMEOUT_SECONDS = 10


def find_tool(name: str) -> Path | None:
    """Return the path of the program ``name`` on PATH, or None if it is not there.

    Unlike ``shutil.which`` on Windows, it never takes the program from the current directory,
    where a cloned repository could have put one. Relative entries of PATH are skipped for the
    same reason.
    """
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        directory = Path(entry)
        if directory.is_absolute() and (found := shutil.which(directory / name)):
            return Path(found)
    return None


def tool_version(tool: Path) -> str:
    """Return the version that a program reports with ``--version``.

    Raises:
        OSError: If the program does not run, does not answer or exits with an error.
    """
    output = _output(tool, _run(tool, "--version"))
    # uv prints "uv 0.13.6 (...)" and git "git version 2.51.0".
    return next((word for word in output.split() if word[:1].isdigit()), output.strip())


def git_config(git: Path, key: str) -> str | None:
    """Return a value of the git configuration that applies here, or None if it is not set.

    Raises:
        OSError: If git does not run, does not answer or cannot read its configuration.
    """
    result = _run(git, "config", "--get", key)
    # git exits with 1 when the key is not set.
    if result.returncode == 1:
        return None
    return _output(git, result).strip() or None


def _run(tool: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    # Files rather than pipes: on Windows, a launcher such as git.exe in Git\cmd starts a child
    # that keeps a pipe open, and after a timeout the wait would last as long as the child.
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        try:
            process = subprocess.run(
                [tool, *arguments],
                stdout=stdout,
                stderr=stderr,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise OSError(f"{tool} did not answer within {_TIMEOUT_SECONDS} seconds.") from error
        except OSError as error:
            # Windows puts %1 where the name of the program belongs.
            reason = (error.strerror or str(error)).replace("%1", tool.name)
            raise OSError(f"{tool} does not run: {reason}") from error
        return subprocess.CompletedProcess(
            process.args, process.returncode, _text(stdout), _text(stderr)
        )


def _text(file: IO[bytes]) -> str:
    file.seek(0)
    # git prints a name from its configuration in UTF-8, whatever the console uses.
    return file.read().decode("utf-8", errors="replace")


def _output(tool: Path, result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode == 0:
        return result.stdout
    reason = result.stderr.strip().splitlines()
    detail = f": {reason[0].strip()}" if reason else "."
    raise OSError(f"{tool} exited with code {result.returncode}{detail}")
