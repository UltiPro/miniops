from pathlib import Path

import pytest

from miniops.config.model import Flavor, load_model_config
from miniops.core.entities import Task
from miniops.core.errors import ConfigError

VALID = """\
[model]
name = "churn"
flavor = "sklearn"
task = "binary_classification"
entrypoint = "model.py:Churn"
"""


def write_config(directory: Path, text: str) -> None:
    (directory / "model.toml").write_text(text, encoding="utf-8")


def test_a_model_config_is_read_from_the_model_directory(tmp_path: Path) -> None:
    write_config(tmp_path, VALID)

    model = load_model_config(tmp_path).model

    assert model.name == "churn"
    assert model.flavor is Flavor.SKLEARN
    assert model.task is Task.BINARY_CLASSIFICATION
    assert model.entrypoint == "model.py:Churn"


@pytest.mark.parametrize(
    ("line", "changed", "problem"),
    [
        ('name = "churn"', 'name = "Churn"', "model.name: .*Invalid model name"),
        ('name = "churn"', 'name = "nul"', "model.name: .*Windows keeps this name"),
        ('flavor = "sklearn"', 'flavor = "keras"', "model.flavor: "),
        ('task = "binary_classification"', 'task = "clustering"', "model.task: "),
        ('entrypoint = "model.py:Churn"', 'entrypoint = "model.py"', "model.entrypoint: "),
        ('entrypoint = "model.py:Churn"', 'entrypoint = "../model.py:Churn"', "model.entrypoint: "),
        ('entrypoint = "model.py:Churn"', "", "model.entrypoint: "),
        ('flavor = "sklearn"', 'flavor = "sklearn"\nframework = "sklearn"', "model.framework: "),
    ],
)
def test_a_model_config_that_is_not_valid_names_the_problem(
    tmp_path: Path, line: str, changed: str, problem: str
) -> None:
    write_config(tmp_path, VALID.replace(line, changed))

    with pytest.raises(ConfigError, match=problem):
        load_model_config(tmp_path)
