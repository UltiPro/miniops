import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from miniops.core.errors import AlreadyExistsError, ConfigError

CONFIG_FILE = "miniops.toml"
STATE_DIR = ".miniops"


class Target(StrEnum):
    """Where models are trained and served."""

    LOCAL = "local"


class _Table(BaseModel):
    # An unknown key is almost always a typo.
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectSection(_Table):
    """The ``[project]`` table of ``miniops.toml``."""

    name: str = Field(min_length=1)
    default_target: Target = Target.LOCAL


class ProjectConfig(_Table):
    """The content of ``miniops.toml``."""

    project: ProjectSection


@dataclass(frozen=True)
class Project:
    """A miniOPs project: its directory and its configuration."""

    root: Path
    config: ProjectConfig


def find_project(start: Path) -> Project:
    """Return the project that ``start`` is in: the directory itself or the nearest parent.

    Raises:
        ConfigError: If there is no project, or its ``miniops.toml`` is not valid.
    """
    root = find_root(start)
    if root is None:
        raise ConfigError(
            f"No miniOPs project in {start} or above it. Create one with `miniops init`."
        )
    return Project(root=root, config=_load(root / CONFIG_FILE))


def init_project(root: Path, name: str | None = None) -> Project:
    """Turn a directory into a project: write ``miniops.toml`` and keep local state out of git.

    The project is named after the directory unless ``name`` is given.

    Raises:
        AlreadyExistsError: If the directory is a project already, or lies inside one.
        ConfigError: If the project would have no name.
    """
    existing = find_root(root)
    if existing is not None:
        raise AlreadyExistsError(f"There is already a miniOPs project in {existing}.")
    name = (name or root.name).strip()
    if not name:
        raise ConfigError("The project needs a name. Pass one with --name.")

    config_file = root / CONFIG_FILE
    config_file.write_text(
        f'[project]\nname = {json.dumps(name, ensure_ascii=False)}\ndefault_target = "local"\n',
        encoding="utf-8",
        newline="\n",
    )
    _ignore_state(root)
    return Project(root=root, config=_load(config_file))


def find_root(start: Path) -> Path | None:
    """Return the directory of the project that ``start`` is in, or None.

    It only looks for ``miniops.toml`` and does not read it.
    """
    start = start.resolve()
    for directory in (start, *start.parents):
        if (directory / CONFIG_FILE).is_file():
            return directory
    return None


def _load(path: Path) -> ProjectConfig:
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as error:
        problems = "\n".join(
            f"  {'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        raise ConfigError(f"{path} is not valid:\n{problems}") from error


def _ignore_state(root: Path) -> None:
    gitignore = root / ".gitignore"
    existing = gitignore.read_bytes() if gitignore.exists() else b""
    patterns = {line.strip().strip(b"/") for line in existing.splitlines()}
    if STATE_DIR.encode() in patterns:
        return
    # Append bytes, so the lines that are already in the file keep their line endings.
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    separator = b"" if not existing or existing.endswith(b"\n") else newline
    with gitignore.open("ab") as file:
        file.write(separator + f"{STATE_DIR}/".encode() + newline)
