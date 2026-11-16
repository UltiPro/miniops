from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniops.adapters.stores import open_stores
from miniops.cli import app
from miniops.config.model import load_model_config
from miniops.config.project import init_project
from miniops.core.errors import AlreadyExistsError, ConfigError
from miniops.core.versions import FIRST_VERSION

runner = CliRunner()
NEW_CHURN = ["new", "churn", "--flavor", "sklearn", "--task", "binary_classification"]


def test_new_creates_a_model_in_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, NEW_CHURN)

    assert result.exit_code == 0
    assert "'churn'" in result.stdout
    assert "1.0.0" in result.stdout
    assert load_model_config(tmp_path / "models" / "churn").model.name == "churn"
    with open_stores(project) as stores:
        model = stores.metadata.get_model("churn")
        assert model is not None
        versions = stores.metadata.list_versions(model.id)
    assert [version.number for version in versions] == [FIRST_VERSION]


def test_new_works_from_a_directory_inside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    inside = tmp_path / "notebooks"
    inside.mkdir()
    monkeypatch.chdir(inside)

    result = runner.invoke(app, NEW_CHURN)

    assert result.exit_code == 0
    assert (tmp_path / "models" / "churn" / "model.toml").is_file()
    assert list(inside.iterdir()) == []


def test_new_twice_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, NEW_CHURN)

    result = runner.invoke(app, NEW_CHURN)

    assert result.exit_code == 1
    assert isinstance(result.exception, AlreadyExistsError)


def test_new_needs_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, NEW_CHURN)

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "arguments",
    [
        ["new", "Churn", "--flavor", "sklearn", "--task", "regression"],
        ["new", "nul", "--flavor", "sklearn", "--task", "regression"],
        ["new", "churn", "--flavor", "sklearn"],
        ["new", "churn", "--task", "regression"],
        ["new", "churn", "--flavor", "keras", "--task", "regression"],
        ["new", "churn", "--flavor", "sklearn", "--task", "clustering"],
    ],
)
def test_new_refuses_arguments_that_are_not_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert not (tmp_path / "models").exists()
