import os
from pathlib import Path

from miniops.core.errors import NotFoundError, ToolError
from miniops.tools import find_tool, run_tool

UV_INSTALL = "https://docs.astral.sh/uv/getting-started/installation/"
# Each would give the model another environment or Python than its own, or make uv warn
# that the active environment, such as the one of miniOPs, is not used.
_REDIRECTS = ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON")


def sync_environment(directory: Path) -> None:
    """Create or update the environment of the model in ``directory`` with uv.

    The environment is ``.venv`` there and follows the ``pyproject.toml`` and ``uv.lock`` of
    the model; uv writes the lock when it is missing.

    Raises:
        NotFoundError: If the directory or its ``pyproject.toml`` is missing.
        ToolError: If uv is missing or fails, or puts the environment elsewhere.
        OSError: If uv does not run.
    """
    if not directory.is_dir():
        raise NotFoundError(f"There is no model directory {directory}.")
    if not (directory / "pyproject.toml").is_file():
        raise NotFoundError(
            f"{directory} has no pyproject.toml, which the environment of a model is made from."
        )
    uv = find_tool("uv")
    if uv is None:
        raise ToolError(f"uv was not found. Install it: {UV_INSTALL}")
    env = {name: value for name, value in os.environ.items() if name not in _REDIRECTS}
    run_tool(uv, "sync", "--project", str(directory), env=env)
    if not (directory / ".venv").is_dir():
        raise ToolError(
            f"uv did not create {directory / '.venv'}. The model is probably a member of a uv "
            "workspace, but it needs an environment of its own."
        )
