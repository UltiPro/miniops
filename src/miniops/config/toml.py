import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from miniops.core.errors import ConfigError


class Table(BaseModel):
    """A table of a configuration file."""

    # An unknown key is almost always a typo.
    model_config = ConfigDict(extra="forbid", frozen=True)


def load[T: BaseModel](path: Path, schema: type[T]) -> T:
    """Read a TOML file and check it against ``schema``.

    Raises:
        ConfigError: If the file is not valid TOML or does not fit the schema.
    """
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    try:
        return schema.model_validate(data)
    except ValidationError as error:
        problems = "\n".join(
            f"  {'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        raise ConfigError(f"{path} is not valid:\n{problems}") from error
