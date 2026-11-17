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
        ConfigError: If the file is missing, is not UTF-8 TOML or does not fit the schema.
    """
    try:
        # Some Windows editors start a UTF-8 file with a byte order mark.
        text = path.read_bytes().decode("utf-8-sig")
    except FileNotFoundError as error:
        raise ConfigError(f"{path} does not exist.") from error
    except UnicodeDecodeError as error:
        raise ConfigError(f"{path} is not saved as UTF-8 text.") from error
    try:
        data = tomllib.loads(text)
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
