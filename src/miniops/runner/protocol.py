import json
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from miniops import __version__
from miniops.core.entities import Signature, Task
from miniops.core.errors import ProtocolError

PROTOCOL: Final = 1
RESULT_FILE = "result.json"
# A backslash would be part of a file name on Linux, where a job can run in a container.
_PATH = r"^[^\\]+$"


class _File(BaseModel):
    # TOML allows inf and nan, which plain JSON cannot hold; Python's json reads these constants.
    model_config = ConfigDict(extra="forbid", frozen=True, ser_json_inf_nan="constants")


class TrainJob(_File):
    """A training for the runner in the environment of a model.

    Paths are relative to the job file, or absolute, and use ``/``.
    """

    protocol: Literal[1] = PROTOCOL
    kind: Literal["train"] = "train"
    model: str = Field(pattern=_PATH, description="The directory with the code of the model.")
    entrypoint: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*\.py:[A-Za-z_][A-Za-z0-9_]*$")
    task: Task
    params: dict[str, JsonValue] = Field(default_factory=dict)
    data: str = Field(pattern=_PATH, description="The Parquet file to train on.")
    target: str
    output: str = Field(
        pattern=_PATH, description="The directory for the files of the model and the result."
    )


class Environment(_File):
    """Where a job ran."""

    miniops: str
    python: str
    platform: str
    machine: str


class Failure(_File):
    """Why a job failed."""

    type: str
    message: str
    reported: bool = Field(description="An error that miniOPs reports itself, like bad data.")


class Result(_File):
    """What a job left. It failed when ``failure`` is set."""

    protocol: Literal[1] = PROTOCOL
    environment: Environment
    signature: Signature | None = None
    files: tuple[str, ...] = Field(default=(), description="Paths in the model directory.")
    untrusted_types: tuple[str, ...] = ()
    failure: Failure | None = None


def write_job(job: TrainJob, path: Path) -> None:
    """Write ``job`` to ``path``."""
    _write(path, job.model_dump_json(indent=2))


def read_job(path: Path) -> TrainJob:
    """Read the job in ``path``.

    Raises:
        ProtocolError: If it is not a job file, or one of a newer protocol.
    """
    return _read(path, TrainJob, "job")


def write_result(result: Result, path: Path) -> None:
    """Write ``result`` to ``path``. The file appears only when it is complete."""
    _write(path, result.model_dump_json(indent=2))


def read_result(path: Path) -> Result:
    """Read the result in ``path``.

    Raises:
        ProtocolError: If it is not a result file, or one of a newer protocol.
    """
    return _read(path, Result, "result")


def _read[T: _File](path: Path, schema: type[T], kind: str) -> T:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError(f"{path} is not a {kind} file of miniOPs: {error}") from error
    version = data.get("protocol") if isinstance(data, dict) else None
    if isinstance(version, int) and version > PROTOCOL:
        raise ProtocolError(
            f"{path} uses protocol {version}, but miniOPs {__version__} reads up to protocol "
            f"{PROTOCOL}. Update the miniOPs that reads it."
        )
    try:
        return schema.model_validate(data)
    except ValidationError as error:
        raise ProtocolError(f"{path} is not a valid {kind} file: {error}") from error


def _write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)
