from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field

from miniops.config.toml import Table, load
from miniops.core.entities import Task, require_name

MODEL_FILE = "model.toml"


class Flavor(StrEnum):
    """The framework a model is built with."""

    SKLEARN = "sklearn"


def _model_name(name: str) -> str:
    require_name("model", name)
    return name


class ModelSection(Table):
    """The ``[model]`` table of ``model.toml``."""

    name: Annotated[str, AfterValidator(_model_name)]
    flavor: Flavor
    task: Task
    # A file and a class in it, like "model.py:Churn".
    entrypoint: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*\.py:[A-Za-z_][A-Za-z0-9_]*$")


class ModelConfig(Table):
    """The content of ``model.toml``."""

    model: ModelSection


def load_model_config(directory: Path) -> ModelConfig:
    """Read the ``model.toml`` of a model directory.

    Raises:
        ConfigError: If the file is not valid.
    """
    return load(directory / MODEL_FILE, ModelConfig)
